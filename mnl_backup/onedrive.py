from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import quote, urlencode
import urllib.error
import urllib.request


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
CHUNK_SIZE = 5 * 1024 * 1024


class OneDriveError(RuntimeError):
    pass


@dataclass
class OneDriveConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    drive_id: str

    @classmethod
    def from_env(cls) -> "OneDriveConfig":
        tenant_id = _clean_env_value(os.environ.get("MNL_ONEDRIVE_TENANT_ID", ""))
        client_id = _clean_env_value(os.environ.get("MNL_ONEDRIVE_CLIENT_ID", ""))
        client_secret = _clean_env_value(os.environ.get("MNL_ONEDRIVE_CLIENT_SECRET", ""))
        drive_id = _clean_env_value(os.environ.get("MNL_ONEDRIVE_DRIVE_ID", ""))
        missing = [
            name
            for name, value in (
                ("MNL_ONEDRIVE_TENANT_ID", tenant_id),
                ("MNL_ONEDRIVE_CLIENT_ID", client_id),
                ("MNL_ONEDRIVE_CLIENT_SECRET", client_secret),
                ("MNL_ONEDRIVE_DRIVE_ID", drive_id),
            )
            if not value
        ]
        if missing:
            raise OneDriveError(f"Missing OneDrive configuration: {', '.join(missing)}")
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            drive_id=drive_id,
        )


class OneDriveClient:
    def __init__(self, config: OneDriveConfig) -> None:
        self.config = config
        self._access_token: Optional[str] = None

    def upload_file(self, local_path: Path, remote_parts: Iterable[str]) -> Dict[str, object]:
        local_path = Path(local_path)
        parts = [part.strip("/") for part in remote_parts if part.strip("/")]
        if not parts:
            raise OneDriveError("remote_parts must contain at least a file name")

        parent_id = self.ensure_folder(parts[:-1])
        file_name = parts[-1]
        upload_url = self._create_upload_session(parent_id=parent_id, file_name=file_name)
        return self._upload_bytes(upload_url=upload_url, local_path=local_path)

    def upload_to_path(self, local_path: Path, remote_path: str) -> Dict[str, object]:
        return self.upload_file(local_path=local_path, remote_parts=_split_remote_path(remote_path))

    def upload_directory(self, local_dir: Path, remote_parts: Iterable[str]) -> Dict[str, object]:
        local_dir = Path(local_dir)
        if not local_dir.exists() or not local_dir.is_dir():
            raise OneDriveError(f"Local directory does not exist: {local_dir}")

        cleaned_remote_parts = [part.strip("/") for part in remote_parts if part.strip("/")]
        if not cleaned_remote_parts:
            raise OneDriveError("remote_parts must contain at least one folder name")

        uploaded = []
        for path in sorted(local_dir.rglob("*")):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(local_dir).parts
            self.upload_file(path, [*cleaned_remote_parts, *rel_parts])
            uploaded.append("/".join([*cleaned_remote_parts, *rel_parts]))

        return {
            "remote_dir": "/".join(cleaned_remote_parts),
            "file_count": len(uploaded),
        }

    def upload_directory_to_path(self, local_dir: Path, remote_path: str) -> Dict[str, object]:
        return self.upload_directory(local_dir=local_dir, remote_parts=_split_remote_path(remote_path))

    def download_file(
        self,
        remote_parts: Iterable[str],
        local_path: Path,
        missing_ok: bool = False,
    ) -> Optional[Path]:
        local_path = Path(local_path)
        item = self.resolve_item(remote_parts)
        if item is None:
            if missing_ok:
                return None
            raise OneDriveError("Remote OneDrive path does not exist")
        if "folder" in item:
            raise OneDriveError("Remote OneDrive path points to a folder, not a file")

        item_id = item.get("id")
        if not item_id:
            raise OneDriveError("Resolved OneDrive item did not include an id")
        metadata = self._graph_json(
            "GET",
            f"{GRAPH_BASE_URL}/drives/{quote(self.config.drive_id)}/items/{quote(str(item_id))}",
        )
        download_url = metadata.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise OneDriveError("Resolved OneDrive file did not include a download URL")

        local_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(str(download_url), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise OneDriveError(
                f"Failed to download OneDrive file: {exc.read().decode('utf-8', 'replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OneDriveError(f"Failed to download OneDrive file: {exc}") from exc

        local_path.write_bytes(payload)
        return local_path

    def download_from_path(
        self,
        remote_path: str,
        local_path: Path,
        missing_ok: bool = False,
    ) -> Optional[Path]:
        return self.download_file(
            remote_parts=_split_remote_path(remote_path),
            local_path=local_path,
            missing_ok=missing_ok,
        )

    def ensure_folder(self, parts: Iterable[str]) -> str:
        parent_id = self.get_approot_id()
        for part in parts:
            parent_id = self._ensure_child_folder(parent_id=parent_id, folder_name=part)
        return parent_id

    def resolve_item(self, parts: Iterable[str]) -> Optional[Dict[str, object]]:
        cleaned_parts = [part.strip("/") for part in parts if part.strip("/")]
        if not cleaned_parts:
            return None

        parent_id = self.get_approot_id()
        item: Optional[Dict[str, object]] = None
        for index, part in enumerate(cleaned_parts):
            item = self._find_child_by_name(parent_id=parent_id, name=part)
            if item is None:
                return None
            if index != len(cleaned_parts) - 1:
                if "folder" not in item:
                    raise OneDriveError(f"Remote path segment is not a folder: {part}")
                parent_id = str(item["id"])
        return item

    def get_approot_id(self) -> str:
        payload = self._graph_json(
            "GET",
            f"{GRAPH_BASE_URL}/drives/{quote(self.config.drive_id)}/special/approot",
        )
        item_id = payload.get("id")
        if not item_id:
            raise OneDriveError("Could not resolve OneDrive approot id")
        return str(item_id)

    def _ensure_child_folder(self, parent_id: str, folder_name: str) -> str:
        child = self._find_child_by_name(parent_id=parent_id, name=folder_name)
        if child:
            if "folder" not in child:
                raise OneDriveError(f"OneDrive item already exists and is not a folder: {folder_name}")
            return str(child["id"])

        payload = self._graph_json(
            "POST",
            f"{GRAPH_BASE_URL}/drives/{quote(self.config.drive_id)}/items/{quote(parent_id)}/children",
            body={
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "replace",
            },
            expected_status=(200, 201),
        )
        item_id = payload.get("id")
        if not item_id:
            raise OneDriveError(f"Failed to create OneDrive folder: {folder_name}")
        return str(item_id)

    def _find_child_by_name(self, parent_id: str, name: str) -> Optional[Dict[str, object]]:
        payload = self._graph_json(
            "GET",
            f"{GRAPH_BASE_URL}/drives/{quote(self.config.drive_id)}/items/{quote(parent_id)}/children"
            "?$select=id,name,folder,file",
        )
        for item in payload.get("value", []):
            if item.get("name") == name:
                return item
        return None

    def _create_upload_session(self, parent_id: str, file_name: str) -> str:
        payload = self._graph_json(
            "POST",
            f"{GRAPH_BASE_URL}/drives/{quote(self.config.drive_id)}/items/{quote(parent_id)}:/"
            f"{quote(file_name)}:/createUploadSession",
            body={
                "item": {
                    "@microsoft.graph.conflictBehavior": "replace",
                    "name": file_name,
                }
            },
            expected_status=(200, 201),
        )
        upload_url = payload.get("uploadUrl")
        if not upload_url:
            raise OneDriveError("Upload session response did not include uploadUrl")
        return str(upload_url)

    def _upload_bytes(self, upload_url: str, local_path: Path) -> Dict[str, object]:
        file_size = local_path.stat().st_size
        with local_path.open("rb") as handle:
            offset = 0
            while offset < file_size:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                start = offset
                end = offset + len(chunk) - 1
                response = self._raw_request(
                    "PUT",
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                    },
                    include_bearer=False,
                    expected_status=(200, 201, 202),
                )
                if response:
                    payload = json.loads(response.decode("utf-8"))
                else:
                    payload = {}
                offset = end + 1
                if offset >= file_size:
                    return payload
        raise OneDriveError("Upload session ended before the file finished uploading")

    def _graph_json(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, object]] = None,
        expected_status=(200,),
    ) -> Dict[str, object]:
        raw = self._raw_request(
            method=method,
            url=url,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={} if body is None else {"Content-Type": "application/json"},
            include_bearer=True,
            expected_status=expected_status,
        )
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _raw_request(
        self,
        method: str,
        url: str,
        data: Optional[bytes],
        headers: Dict[str, str],
        include_bearer: bool,
        expected_status=(200,),
    ) -> bytes:
        request_headers = dict(headers)
        if include_bearer:
            request_headers["Authorization"] = f"Bearer {self._get_access_token()}"

        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status_code = response.getcode() or 200
                payload = response.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            payload = exc.read()
            if status_code not in expected_status:
                guidance = ""
                payload_text = payload.decode("utf-8", "replace")
                if (
                    status_code == 400
                    and "/special/approot" in url
                    and "drive id" in payload_text.lower()
                ):
                    guidance = (
                        " Check MNL_ONEDRIVE_DRIVE_ID. It must be the raw drive 'id' value from "
                        "SharePoint/Graph, pasted without quotes, commas, or extra spaces."
                    )
                raise OneDriveError(
                    f"OneDrive request failed ({status_code}) for {method} {url}: {payload_text}{guidance}"
                ) from exc
        except urllib.error.URLError as exc:
            raise OneDriveError(f"OneDrive request failed for {method} {url}: {exc}") from exc

        if status_code not in expected_status:
            raise OneDriveError(
                f"Unexpected status {status_code} for {method} {url}: {payload.decode('utf-8', 'replace')}"
            )
        return payload

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        token_url = TOKEN_URL_TEMPLATE.format(tenant_id=quote(self.config.tenant_id))
        body = urlencode(
            {
                "client_id": self.config.client_id,
                "scope": "https://graph.microsoft.com/.default",
                "client_secret": self.config.client_secret,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OneDriveError(
                f"Failed to acquire OneDrive access token: {exc.read().decode('utf-8', 'replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OneDriveError(f"Failed to acquire OneDrive access token: {exc}") from exc

        token = payload.get("access_token")
        if not token:
            raise OneDriveError("Token response did not include access_token")
        self._access_token = str(token)
        return self._access_token


def _clean_env_value(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _split_remote_path(remote_path: str) -> list[str]:
    return [part for part in remote_path.split("/") if part.strip("/")]
