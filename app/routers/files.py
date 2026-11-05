import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.file_manager import file_manager

router = APIRouter(tags=["files"])


class FileSaveRequest(BaseModel):
    path: str
    content: str


class FolderCreateRequest(BaseModel):
    path: str


class UnzipRequest(BaseModel):
    path: str
    target_dir: str = ""


class FileRenameRequest(BaseModel):
    path: str
    new_name: str


class FileDuplicateRequest(BaseModel):
    path: str


class FileCompressRequest(BaseModel):
    path: str


class FileCreateRequest(BaseModel):
    path: str


class BulkDeleteRequest(BaseModel):
    paths: List[str]


class BulkCompressRequest(BaseModel):
    paths: List[str]
    target_dir: Optional[str] = ""
    archive_name: Optional[str] = ""


@router.get("/api/files/list", dependencies=[Depends(get_current_user)])
async def file_list(path: str = Query("")):
    return file_manager.list_directory(path)


@router.get("/api/files/content", dependencies=[Depends(get_current_user)])
async def file_content(path: str = Query(...)):
    return file_manager.read_file(path)


@router.post("/api/files/save", dependencies=[Depends(get_current_user)])
async def file_save(req: FileSaveRequest):
    return file_manager.write_file(req.path, req.content)


@router.post("/api/files/folder", dependencies=[Depends(get_current_user)])
async def file_folder(req: FolderCreateRequest):
    return file_manager.create_folder(req.path)


@router.delete("/api/files/delete", dependencies=[Depends(get_current_user)])
async def file_delete(path: str = Query(...)):
    return file_manager.delete_item(path)


@router.post("/api/files/upload", dependencies=[Depends(get_current_user)])
async def file_upload(path: str = Form(""), file: UploadFile = File(...)):
    return await file_manager.save_upload(path, file)


@router.post("/api/files/unzip", dependencies=[Depends(get_current_user)])
async def file_unzip(req: UnzipRequest):
    return await asyncio.to_thread(file_manager.extract_zip, req.path, req.target_dir)


@router.get("/api/files/download", dependencies=[Depends(get_current_user)])
async def file_download(path: str = Query(...)):
    safe_path = file_manager._resolve_safe_path(path)
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(safe_path),
        filename=safe_path.name,
        media_type="application/octet-stream"
    )


@router.post("/api/files/rename", dependencies=[Depends(get_current_user)])
async def file_rename(req: FileRenameRequest):
    return file_manager.rename_item(req.path, req.new_name)


@router.post("/api/files/duplicate", dependencies=[Depends(get_current_user)])
async def file_duplicate(req: FileDuplicateRequest):
    return file_manager.duplicate_item(req.path)


@router.post("/api/files/compress", dependencies=[Depends(get_current_user)])
async def file_compress(req: FileCompressRequest):
    return await asyncio.to_thread(file_manager.compress_item, req.path)


@router.post("/api/files/create", dependencies=[Depends(get_current_user)])
async def file_create(req: FileCreateRequest):
    return file_manager.create_file(req.path)


@router.post("/api/files/bulk-delete", dependencies=[Depends(get_current_user)])
async def file_bulk_delete(req: BulkDeleteRequest):
    return file_manager.bulk_delete(req.paths)


@router.post("/api/files/bulk-compress", dependencies=[Depends(get_current_user)])
async def file_bulk_compress(req: BulkCompressRequest):
    return await asyncio.to_thread(file_manager.bulk_compress, req.paths, req.target_dir or "", req.archive_name or "")

