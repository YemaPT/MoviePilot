import traceback
from pathlib import Path
from typing import Optional, Any, Tuple, List, Set, Union, Dict

from ruamel.yaml import CommentedMap

from app.core.context import Context
from app.core.context import MediaInfo, TorrentInfo
from app.core.event import EventManager
from app.core.meta import MetaBase
from app.core.module import ModuleManager
from app.log import logger
from app.schemas import TransferInfo, TransferTorrent, ExistMediaInfo, DownloadingTorrent
from app.schemas.types import TorrentStatus, MediaType
from app.utils.singleton import AbstractSingleton, Singleton


class ChainBase(AbstractSingleton, metaclass=Singleton):
    """
    处理链基类
    """

    def __init__(self):
        """
        公共初始化
        """
        self.modulemanager = ModuleManager()
        self.eventmanager = EventManager()

    def __run_module(self, method: str, *args, **kwargs) -> Any:
        """
        运行包含该方法的所有模块，然后返回结果
        """

        def is_result_empty(ret):
            """
            判断结果是否为空
            """
            if isinstance(ret, tuple):
                return all(value is None for value in ret)
            else:
                return result is None

        logger.debug(f"请求模块执行：{method} ...")
        result = None
        modules = self.modulemanager.get_modules(method)
        for module in modules:
            try:
                if is_result_empty(result):
                    # 返回None，第一次执行或者需继续执行下一模块
                    result = getattr(module, method)(*args, **kwargs)
                else:
                    if isinstance(result, list):
                        # 返回为列表，有多个模块运行结果时进行合并（不能多个模块同时运行的需要通过开关控制）
                        temp = getattr(module, method)(*args, **kwargs)
                        if isinstance(temp, list):
                            result.extend(temp)
                    else:
                        # 返回结果非列表也非空，则执行一次后跳出
                        break
            except Exception as err:
                logger.error(f"运行模块 {method} 出错：{module.__class__.__name__} - {err}\n{traceback.print_exc()}")
        return result

    def prepare_recognize(self, title: str,
                          subtitle: str = None) -> Tuple[str, str]:
        """
        处理各类特别命名，以便识别
        :param title:     标题
        :param subtitle:  副标题
        :return: 处理后的标题、副标题，该方法可被多个模块同时处理
        """
        return self.__run_module("prepare_recognize", title=title, subtitle=subtitle)

    def recognize_media(self, meta: MetaBase = None,
                        mtype: MediaType = None,
                        tmdbid: int = None) -> Optional[MediaInfo]:
        """
        识别媒体信息
        :param meta:     识别的元数据
        :param mtype:    识别的媒体类型，与tmdbid配套
        :param tmdbid:   tmdbid
        :return: 识别的媒体信息，包括剧集信息
        """
        return self.__run_module("recognize_media", meta=meta, mtype=mtype, tmdbid=tmdbid)

    def obtain_image(self, mediainfo: MediaInfo) -> Optional[MediaInfo]:
        """
        获取图片
        :param mediainfo:  识别的媒体信息
        :return: 更新后的媒体信息
        """
        return self.__run_module("obtain_image", mediainfo=mediainfo)

    def douban_info(self, doubanid: str) -> Optional[dict]:
        """
        获取豆瓣信息
        :param doubanid: 豆瓣ID
        :return: 豆瓣信息
        """
        return self.__run_module("douban_info", doubanid=doubanid)

    def tvdb_info(self, tvdbid: int) -> Optional[dict]:
        """
        获取TVDB信息
        :param tvdbid: int
        :return: TVDB信息
        """
        return self.__run_module("tvdb_info", tvdbid=tvdbid)

    def tmdb_info(self, tmdbid: int, mtype: MediaType) -> Optional[dict]:
        """
        获取TMDB信息
        :param tmdbid: int
        :param mtype:  媒体类型
        :return: TVDB信息
        """
        return self.__run_module("tmdb_info", tmdbid=tmdbid, mtype=mtype)

    def message_parser(self, body: Any, form: Any, args: Any) -> Optional[dict]:
        """
        解析消息内容，返回字典，注意以下约定值：
        userid: 用户ID
        username: 用户名
        text: 内容
        :param body: 请求体
        :param form: 表单
        :param args: 参数
        :return: 消息内容、用户ID
        """
        return self.__run_module("message_parser", body=body, form=form, args=args)

    def webhook_parser(self, body: Any, form: Any, args: Any) -> Optional[dict]:
        """
        解析Webhook报文体
        :param body:  请求体
        :param form:  请求表单
        :param args:  请求参数
        :return: 字典，解析为消息时需要包含：title、text、image
        """
        return self.__run_module("webhook_parser", body=body, form=form, args=args)

    def search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        搜索媒体信息
        :param meta:  识别的元数据
        :reutrn: 媒体信息列表
        """
        return self.__run_module("search_medias", meta=meta)

    def search_torrents(self, mediainfo: Optional[MediaInfo], sites: List[CommentedMap],
                        keyword: str = None) -> Optional[List[TorrentInfo]]:
        """
        搜索站点，多个站点需要多线程处理
        :param mediainfo:  识别的媒体信息
        :param sites:  站点列表
        :param keyword:  搜索关键词，如有按关键词搜索，否则按媒体信息名称搜索
        :reutrn: 资源列表
        """
        return self.__run_module("search_torrents", mediainfo=mediainfo, sites=sites, keyword=keyword)

    def refresh_torrents(self, sites: List[CommentedMap]) -> Optional[List[TorrentInfo]]:
        """
        获取站点最新一页的种子，多个站点需要多线程处理
        :param sites:  站点列表
        :reutrn: 种子资源列表
        """
        return self.__run_module("refresh_torrents", sites=sites)

    def filter_torrents(self, torrent_list: List[TorrentInfo],
                        season_episodes: Dict[int, list] = None) -> List[TorrentInfo]:
        """
        过滤种子资源
        :param torrent_list:  资源列表
        :param season_episodes:  季集数过滤 {season:[episodes]}
        :return: 过滤后的资源列表，添加资源优先级
        """
        return self.__run_module("filter_torrents", torrent_list=torrent_list, season_episodes=season_episodes)

    def download(self, torrent_path: Path, cookie: str,
                 episodes: Set[int] = None) -> Optional[Tuple[Optional[str], str]]:
        """
        根据种子文件，选择并添加下载任务
        :param torrent_path:  种子文件地址
        :param cookie:  cookie
        :param episodes:  需要下载的集数
        :return: 种子Hash，错误信息
        """
        return self.__run_module("download", torrent_path=torrent_path, cookie=cookie, episodes=episodes)

    def download_added(self, context: Context, torrent_path: Path) -> None:
        """
        添加下载任务成功后，从站点下载字幕，保存到下载目录
        :param context:  上下文，包括识别信息、媒体信息、种子信息
        :param torrent_path:  种子文件地址
        :return: None，该方法可被多个模块同时处理
        """
        return self.__run_module("download_added", context=context, torrent_path=torrent_path)

    def list_torrents(self, status: TorrentStatus = None,
                      hashs: Union[list, str] = None) -> Optional[List[Union[TransferTorrent, DownloadingTorrent]]]:
        """
        获取下载器种子列表
        :param status:  种子状态
        :param hashs:  种子Hash
        :return: 下载器中符合状态的种子列表
        """
        return self.__run_module("list_torrents", status=status, hashs=hashs)

    def transfer(self, path: Path, mediainfo: MediaInfo) -> Optional[TransferInfo]:
        """
        文件转移
        :param path:  文件路径
        :param mediainfo:  识别的媒体信息
        :return: {path, target_path, message}
        """
        return self.__run_module("transfer", path=path, mediainfo=mediainfo)

    def transfer_completed(self, hashs: Union[str, list], transinfo: TransferInfo) -> None:
        """
        转移完成后的处理
        :param hashs:  种子Hash
        :param transinfo:  转移信息
        """
        return self.__run_module("transfer_completed", hashs=hashs, transinfo=transinfo)

    def remove_torrents(self, hashs: Union[str, list]) -> bool:
        """
        删除下载器种子
        :param hashs:  种子Hash
        :return: bool
        """
        return self.__run_module("remove_torrents", hashs=hashs)

    def media_exists(self, mediainfo: MediaInfo) -> Optional[ExistMediaInfo]:
        """
        判断媒体文件是否存在
        :param mediainfo:  识别的媒体信息
        :return: 如不存在返回None，存在时返回信息，包括每季已存在所有集{type: movie/tv, seasons: {season: [episodes]}}
        """
        return self.__run_module("media_exists", mediainfo=mediainfo)

    def refresh_mediaserver(self, mediainfo: MediaInfo, file_path: Path) -> Optional[bool]:
        """
        刷新媒体库
        :param mediainfo:  识别的媒体信息
        :param file_path:  文件路径
        :return: 成功或失败
        """
        return self.__run_module("refresh_mediaserver", mediainfo=mediainfo, file_path=file_path)

    def post_message(self, title: str, text: str = None,
                     image: str = None, userid: Union[str, int] = None) -> Optional[bool]:
        """
        发送消息
        :param title:  标题
        :param text: 内容
        :param image: 图片
        :param userid:  用户ID
        :return: 成功或失败
        """
        return self.__run_module("post_message", title=title, text=text, image=image, userid=userid)

    def post_medias_message(self, title: str, items: List[MediaInfo],
                            userid: Union[str, int] = None) -> Optional[bool]:
        """
        发送媒体信息选择列表
        :param title:  标题
        :param items:  消息列表
        :param userid:  用户ID
        :return: 成功或失败
        """
        return self.__run_module("post_medias_message", title=title, items=items, userid=userid)

    def post_torrents_message(self, title: str, items: List[Context],
                              mediainfo: MediaInfo,
                              userid: Union[str, int] = None) -> Optional[bool]:
        """
        发送种子信息选择列表
        :param title: 标题
        :param items:  消息列表
        :param mediainfo:  媒体信息
        :param userid:  用户ID
        :return: 成功或失败
        """
        return self.__run_module("post_torrents_message", title=title, mediainfo=mediainfo,
                                 items=items, userid=userid)

    def scrape_metadata(self, path: Path, mediainfo: MediaInfo) -> None:
        """
        刮削元数据
        :param path: 媒体文件路径
        :param mediainfo:  识别的媒体信息
        :return: 成功或失败
        """
        return self.__run_module("scrape_metadata", path=path, mediainfo=mediainfo)

    def register_commands(self, commands: dict) -> None:
        """
        注册菜单命令
        """
        return self.__run_module("register_commands", commands=commands)

    def douban_discover(self, mtype: MediaType, sort: str, tags: str,
                        start: int = 0, count: int = 30) -> Optional[List[dict]]:
        """
        发现豆瓣电影、剧集
        :param mtype:  媒体类型
        :param sort:  排序方式
        :param tags:  标签
        :param start:  起始位置
        :param count:  数量
        :return: 媒体信息列表
        """
        return self.__run_module("douban_discover", mtype=mtype, sort=sort, tags=tags,
                                 start=start, count=count)

    def tmdb_discover(self, mtype: MediaType, sort_by: str, with_genres: str,
                      with_original_language: str, page: int = 1) -> Optional[List[dict]]:
        """
        :param mtype:  媒体类型
        :param sort_by:  排序方式
        :param with_genres:  类型
        :param with_original_language:  语言
        :param page:  页码
        :return: 媒体信息列表
        """
        return self.__run_module("tmdb_discover", mtype=mtype,
                                 sort_by=sort_by, with_genres=with_genres,
                                 with_original_language=with_original_language,
                                 page=page)

    def movie_top250(self, page: int = 1, count: int = 30) -> List[dict]:
        """
        获取豆瓣电影TOP250
        :param page:  页码
        :param count:  每页数量
        """
        return self.__run_module("movie_top250", page=page, count=count)
