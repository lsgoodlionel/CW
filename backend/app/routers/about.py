"""关于系统:版本、开发、反馈、联系、用户手册等信息。仅需登录即可访问。"""
from fastapi import APIRouter

from .. import version
from ..schemas_read import AboutOut

router = APIRouter(prefix="/api", tags=["about"])


@router.get("/about", response_model=AboutOut)
def about():
    return version.about()
