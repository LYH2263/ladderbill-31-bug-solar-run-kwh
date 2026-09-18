class SolarOffsetError(Exception):
    """Base error for the solar_offset module."""


class AccountNotFound(SolarOffsetError):
    """录入/预览指向了未知户号。"""


class OffsetConflict(SolarOffsetError):
    """有效记录冲突：缺少显式版本号或版本号不匹配。"""
