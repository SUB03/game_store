from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AddGameToUserRequest(_message.Message):
    __slots__ = ("username", "appid")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    username: str
    appid: int
    def __init__(self, username: _Optional[str] = ..., appid: _Optional[int] = ...) -> None: ...

class AddGameToUserResponse(_message.Message):
    __slots__ = ("appid",)
    APPID_FIELD_NUMBER: _ClassVar[int]
    appid: int
    def __init__(self, appid: _Optional[int] = ...) -> None: ...

class AddGamesIfNoneOwnedRequest(_message.Message):
    __slots__ = ("username", "appids")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPIDS_FIELD_NUMBER: _ClassVar[int]
    username: str
    appids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, username: _Optional[str] = ..., appids: _Optional[_Iterable[int]] = ...) -> None: ...

class AddGamesIfNoneOwnedResponse(_message.Message):
    __slots__ = ("already_owned",)
    ALREADY_OWNED_FIELD_NUMBER: _ClassVar[int]
    already_owned: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, already_owned: _Optional[_Iterable[int]] = ...) -> None: ...

class HasGameRequest(_message.Message):
    __slots__ = ("username", "appid")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    username: str
    appid: int
    def __init__(self, username: _Optional[str] = ..., appid: _Optional[int] = ...) -> None: ...

class HasGameResponse(_message.Message):
    __slots__ = ("result",)
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: bool
    def __init__(self, result: _Optional[bool] = ...) -> None: ...

class GetOwnedGamesRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class GetOwnedGamesResponse(_message.Message):
    __slots__ = ("appids",)
    APPIDS_FIELD_NUMBER: _ClassVar[int]
    appids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, appids: _Optional[_Iterable[int]] = ...) -> None: ...

class AddGameToCartRequest(_message.Message):
    __slots__ = ("username", "appid")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    username: str
    appid: int
    def __init__(self, username: _Optional[str] = ..., appid: _Optional[int] = ...) -> None: ...

class AddGameToCartResponse(_message.Message):
    __slots__ = ("appid", "added")
    APPID_FIELD_NUMBER: _ClassVar[int]
    ADDED_FIELD_NUMBER: _ClassVar[int]
    appid: int
    added: bool
    def __init__(self, appid: _Optional[int] = ..., added: _Optional[bool] = ...) -> None: ...

class RemoveGameFromCartRequest(_message.Message):
    __slots__ = ("username", "appid")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    username: str
    appid: int
    def __init__(self, username: _Optional[str] = ..., appid: _Optional[int] = ...) -> None: ...

class RemoveGameFromCartResponse(_message.Message):
    __slots__ = ("appid", "removed")
    APPID_FIELD_NUMBER: _ClassVar[int]
    REMOVED_FIELD_NUMBER: _ClassVar[int]
    appid: int
    removed: bool
    def __init__(self, appid: _Optional[int] = ..., removed: _Optional[bool] = ...) -> None: ...

class GetCartRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class GetCartResponse(_message.Message):
    __slots__ = ("appids",)
    APPIDS_FIELD_NUMBER: _ClassVar[int]
    appids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, appids: _Optional[_Iterable[int]] = ...) -> None: ...

class ClearCartRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class ClearCartResponse(_message.Message):
    __slots__ = ("removed",)
    REMOVED_FIELD_NUMBER: _ClassVar[int]
    removed: int
    def __init__(self, removed: _Optional[int] = ...) -> None: ...
