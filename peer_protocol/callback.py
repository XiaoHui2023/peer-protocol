from typing import Callable, Any, Union, get_origin, get_args
from types import UnionType
import inspect
from pydantic import BaseModel
from typing import Awaitable

class Callback:
    """
    回调函数
    
    [注解]

    """
    def __init__(self, function: Union[Callable[..., None], Callable[..., Awaitable[None]]], strict: bool = True):
        """
        Args:
            function: 回调函数
            strict: 是否严格模式
        """
        self.function = function
        self.annotations = self._get_payload_annotation(function)
        self.strict = strict

    def __call__(self, *args: Any) -> Any:
        N = len(self.annotations)
        
        if len(args) < N:
            raise TypeError(
                f"回调只需要 {N} 个参数，实际传入 {len(args)} 个"
            )
        
        if N == 0:
            return self.function(*args)
        
        prepared_args = []
        for i in range(N):
            ok, value = self._prepare_arg(args[i], self.annotations[i])
            if not ok:
                if self.strict:
                    raise TypeError(
                        f"第 {i + 1} 个参数类型不匹配且无法从 dict 转换："
                        f"期望 {self.annotations[i]!r}，实际 {type(args[i]).__name__!r}"
                    )
                return None
            prepared_args.append(value)
        
        return self.function(*prepared_args)

    def _get_payload_annotation(self, fn: Callable) -> list[type]:
        """获取回调参数的类型注解"""
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if not params:
            return []
        annotations = []
        for param in params:
            ann = param.annotation
            if ann is inspect.Parameter.empty or ann is Any:
                ann = Any
            annotations.append(ann)
        return annotations

    def _matches_type(self, data: Any, annotation: type) -> bool:
        """判断数据是否匹配类型注解"""
        if annotation is None or annotation is Any:
            return True
        
        origin = get_origin(annotation)
        
        # UnionType (Python 3.10+ 的 X | Y 语法)
        if origin is UnionType:
            args = get_args(annotation)
            return any(self._matches_type(data, a) for a in args)
                
        # typing.Union (Union[X, Y] 语法)
        if origin is Union:
            args = get_args(annotation)
            return any(self._matches_type(data, a) for a in args)
            
        if origin is not None:
            if origin is dict and isinstance(data, dict):
                return True
            if origin is list and isinstance(data, list):
                return True
            return False
        
        return isinstance(data, annotation)

    def _try_convert(self, data: Any, annotation: type) -> Any | None:
        """尝试将 dict 转为 annotation 类型，失败返回 None"""
        if not isinstance(data, dict):
            return None
        if get_origin(annotation) is not None:
            return None
        
        try:
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                return annotation.model_validate(data)
            else:
                return annotation(**data)
        except Exception:
            return None

    def _prepare_arg(self, data: Any, annotation: type) -> tuple[bool, Any]:
        """准备参数：已匹配则用原值，否则尝试从 dict 转换。返回 (成功?, 最终值)"""
        if self._matches_type(data, annotation):
            return True, data
        converted = self._try_convert(data, annotation)
        if converted is not None:
            return True, converted
        return False, None