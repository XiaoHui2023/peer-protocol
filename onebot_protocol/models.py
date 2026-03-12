from pydantic import BaseModel, Field
from typing import Literal, List, Annotated, Union

class TextSegmentData(BaseModel):
    """纯文本"""
    text: str

class MentionSegmentData(BaseModel):
    """@某人"""
    user_id: str

class MentionAllSegmentData(BaseModel):
    """@所有人"""
    pass

class ImageSegmentData(BaseModel):
    """图片"""
    file_id: str

class VoiceSegmentData(BaseModel):
    """语音"""
    file_id: str

class AudioSegmentData(BaseModel):
    """音频"""
    file_id: str

class VideoSegmentData(BaseModel):
    """视频"""
    file_id: str

class FileSegmentData(BaseModel):
    """文件"""
    file_id: str

class LocationSegmentData(BaseModel):
    """位置"""
    latitude: float
    longitude: float
    title: str
    content: str

class ReplySegmentData(BaseModel):
    """回复"""
    message_id: str
    user_id: str | None = None  # 可选

class TextMessageSegment(BaseModel):
    type: Literal["text"] = "text"
    data: TextSegmentData

class MentionMessageSegment(BaseModel):
    type: Literal["mention"] = "mention"
    data: MentionSegmentData

class MentionAllMessageSegment(BaseModel):
    type: Literal["mention_all"] = "mention_all"
    data: MentionAllSegmentData = Field(default_factory=MentionAllSegmentData)

class ImageMessageSegment(BaseModel):
    type: Literal["image"] = "image"
    data: ImageSegmentData

class VoiceMessageSegment(BaseModel):
    type: Literal["voice"] = "voice"
    data: VoiceSegmentData

class AudioMessageSegment(BaseModel):
    type: Literal["audio"] = "audio"
    data: AudioSegmentData

class VideoMessageSegment(BaseModel):
    type: Literal["video"] = "video"
    data: VideoSegmentData

class FileMessageSegment(BaseModel):
    type: Literal["file"] = "file"
    data: FileSegmentData

class LocationMessageSegment(BaseModel):
    type: Literal["location"] = "location"
    data: LocationSegmentData

class ReplyMessageSegment(BaseModel):
    type: Literal["reply"] = "reply"
    data: ReplySegmentData

MessageSegment = Annotated[
    Union[
        TextMessageSegment,
        MentionMessageSegment,
        MentionAllMessageSegment,
        ImageMessageSegment,
        VoiceMessageSegment,
        AudioMessageSegment,
        VideoMessageSegment,
        FileMessageSegment,
        LocationMessageSegment,
        ReplyMessageSegment,
    ],
    Field(discriminator="type"),
]

class MessagePayload(BaseModel):
    """消息载体"""
    source_type: Literal['group', 'private'] = Field(..., description="消息来源类型")
    session_id: str = Field(..., description="会话 ID")
    bot_id: str = Field(..., description="机器人 ID")
    user_id: str = Field(..., description="用户 ID")
    messages: List[MessageSegment] = Field(..., description="消息列表")