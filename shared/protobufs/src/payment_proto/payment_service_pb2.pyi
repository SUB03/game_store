from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PaymentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PAYMENT_STATUS_UNSPECIFIED: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_PENDING: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_SUCCEEDED: _ClassVar[PaymentStatus]
    PAYMENT_STATUS_FAILED: _ClassVar[PaymentStatus]
PAYMENT_STATUS_UNSPECIFIED: PaymentStatus
PAYMENT_STATUS_PENDING: PaymentStatus
PAYMENT_STATUS_SUCCEEDED: PaymentStatus
PAYMENT_STATUS_FAILED: PaymentStatus

class MakePaymentRequest(_message.Message):
    __slots__ = ("username", "appid", "price", "appids", "idempotency_key")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    APPIDS_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    username: str
    appid: int
    price: str
    appids: _containers.RepeatedScalarFieldContainer[int]
    idempotency_key: str
    def __init__(self, username: _Optional[str] = ..., appid: _Optional[int] = ..., price: _Optional[str] = ..., appids: _Optional[_Iterable[int]] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class MakePaymentResponse(_message.Message):
    __slots__ = ("payment_id", "confirmation_url")
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIRMATION_URL_FIELD_NUMBER: _ClassVar[int]
    payment_id: str
    confirmation_url: str
    def __init__(self, payment_id: _Optional[str] = ..., confirmation_url: _Optional[str] = ...) -> None: ...

class PaymentNotificationRequest(_message.Message):
    __slots__ = ("type", "event", "object")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    type: str
    event: str
    object: _struct_pb2.Struct
    def __init__(self, type: _Optional[str] = ..., event: _Optional[str] = ..., object: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class PaymentNotificationResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: PaymentStatus
    def __init__(self, status: _Optional[_Union[PaymentStatus, str]] = ...) -> None: ...
