import os
import re
import time
import pathlib
import random
import threading
import logging
import sqlite3
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlencode
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# 线程数
THREAD_COUNT = 10

# 线程锁（用于打印输出和日志）
print_lock = threading.Lock()

# 日志配置
LOG_DIR = "logs"
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 创建日志文件名（带时间戳）
log_filename = os.path.join(LOG_DIR, f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),  # 文件日志
        logging.StreamHandler()  # 控制台日志
    ]
)

logger = logging.getLogger(__name__)

# 创建全局 Session 以保持 cookies（主线程使用）
session = requests.Session()

# 多个 User-Agent 列表（随机使用，模拟不同浏览器）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]


def get_random_headers(referer: Optional[str] = None, is_ajax: bool = False) -> Dict[str, str]:
    """生成随机的请求头，模拟真实浏览器"""
    user_agent = random.choice(USER_AGENTS)
    
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document" if not is_ajax else "empty",
        "Sec-Fetch-Mode": "navigate" if not is_ajax else "cors",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "max-age=0",
    }
    
    if is_ajax:
        headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
    else:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    
    if referer:
        headers["Referer"] = referer
    else:
        headers["Referer"] = ALL_URL
    
    return headers


# 基础配置
DOWNLOAD_DIR = "walls"
REQUEST_INTERVAL = 1.0

# 本地数据库配置（用于记录已下载壁纸，避免重复下载）
DB_PATH = "walls.db"

# 全部壁纸URL
ALL_URL = "https://www.dpm.org.cn/lights/royal.html"

# 检索条件URL模板（注意是 royalb.html，不是 royal.html）
FILTER_URL_TEMPLATE = "https://www.dpm.org.cn/searchs/royalb.html"

# 图片下载URL模板
IMG_DOWNLOAD_URL_TEMPLATE = "https://www.dpm.org.cn/download/lights_image/id/{primaryid}/img_size/{size}.html"

# 图片类型：0横版、1竖版、2方形
IMG_TYPE = 0

# 尺寸格式映射（通过实际测试获得）
# 注意：尺寸编号不连续，有些尺寸可能不存在
SIZE_FORMAT_MAP = {
    1: "1920 x 1280",   # 电脑（横版）
    2: "1280 x 800",    # 电脑（横版）
    3: "1680 x 1050",  # 电脑（横版）
    4: "1920 x 1080",  # 电脑（横版）
    6: "1080 x 1920",  # 手机（竖版）
    7: "1125 x 2436",   # 手机（竖版）
    8: "2732 x 2732",   # 平板（方形）
    9: "2048 x 2048",   # 平板（方形）
    11: "1284 x 2778",  # 手机（竖版）
    12: "2560 x 1440",  # 电脑（横版，2K）
    13: "4000 x 2250",  # 电脑（横版，4K）
}

# 按设备类型分组（方便使用）
PX_SIZE_PC = {
    2: "1280 x 800",    # 尺寸2
    3: "1680 x 1050",  # 尺寸3
    1: "1920 x 1280",  # 尺寸1
    4: "1920 x 1080",  # 尺寸4
    12: "2560 x 1440", # 尺寸12（2K）
    13: "4000 x 2250", # 尺寸13（4K）
}

PX_SIZE_PHONE = {
    6: "1080 x 1920",   # 尺寸6
    7: "1125 x 2436",   # 尺寸7
    11: "1284 x 2778",  # 尺寸11
}

PX_SIZE_TABLET = {
    8: "2732 x 2732",   # 尺寸8
    9: "2048 x 2048",  # 尺寸9
}

# 兼容旧代码的映射
PX_SIZE = SIZE_FORMAT_MAP

# 设备类型映射
DEVICE_TYPE_MAP = {
    "is_pc": "电脑",
    "is_wap": "手机",
    "is_calendar": "月历",
    "is_four_k": "4K",
}

# 默认分类ID
DEFAULT_CATEGORY_ID = 624


def init_db(db_path: str = DB_PATH) -> None:
    """初始化本地 SQLite 数据库（如果不存在则创建）。

    主要用于：
    - 记录已经下载过的壁纸，避免重复下载
    - 支持后续做增量扫描 / 订阅
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS wallpapers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primaryid TEXT NOT NULL,
                device   TEXT NOT NULL,   -- 设备类型：电脑/手机/月历/4K 等
                year     TEXT,           -- 年份，如 2026 或 "更早"
                month    TEXT,           -- 月份，如 "02"
                name     TEXT,           -- 壁纸名称
                px       TEXT,           -- 分辨率字符串（与文件名一致），如 "1920x1080"
                rel_path TEXT NOT NULL,  -- 相对路径，例如 "walls/电脑/2026/02/xxx.png"
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(primaryid, px, device)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def normalize_px(px: str) -> str:
    """将分辨率字符串规范化为与文件名一致的格式，例如：
    - "1920 x 1080" -> "1920x1080"
    - "2560*1440" / "2560×1440" -> "2560x1440"
    """
    s = (px or "").strip()
    if not s:
        return ""
    s = s.replace("×", "x").replace("*", "x")
    # 去掉所有空白字符（空格、tab 等）
    s = re.sub(r"\s+", "", s)
    # 合并连续的 x
    s = re.sub(r"x+", "x", s)
    return s


def db_get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """获取一个到 SQLite 的连接。

    不在全局持有长连接，避免多线程下的竞争问题，
    每次操作时打开连接，用完立即关闭即可。
    """
    return sqlite3.connect(db_path, timeout=30)


def db_has_wallpaper(
    primaryid: str,
    px: str,
    device: str,
    db_path: str = DB_PATH,
) -> bool:
    """检查数据库中是否已经存在某个壁纸记录。

    以 (primaryid, px, device) 作为唯一键。
    """
    px_norm = normalize_px(px)
    conn = db_get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM wallpapers
            WHERE primaryid = ? AND px = ? AND device = ?
            LIMIT 1
            """,
            (primaryid, px_norm, device),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def db_upsert_wallpaper(
    primaryid: str,
    device: str,
    year: str,
    month: str,
    name: str,
    px: str,
    rel_path: str,
    db_path: str = DB_PATH,
) -> None:
    """插入或更新一条壁纸记录到数据库。

    - primaryid + px + device 作为唯一键
    - 如果已经存在，则只更新名称、路径等信息
    """
    px_norm = normalize_px(px)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db_get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO wallpapers (
                primaryid, device, year, month, name, px, rel_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(primaryid, px, device) DO UPDATE SET
                year      = excluded.year,
                month     = excluded.month,
                name      = excluded.name,
                rel_path  = excluded.rel_path,
                updated_at = excluded.updated_at
            """,
            (
                primaryid,
                device,
                year,
                month,
                name,
                px_norm,
                rel_path,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

def safe_segment(name: str) -> str:
    """把分类名/中文标题转换为安全的文件夹名"""
    name = (name or "").strip()
    if not name:
        return ""
    # Windows 禁止: \ / : * ? " < > |
    # 同时替换其他可能有问题的字符
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    # 替换多个连续的下划线为单个
    name = re.sub(r'_+', '_', name)
    # 去掉首尾下划线
    name = name.strip('_')
    return name


def fetch(url: str, referer: Optional[str] = None, is_ajax: bool = False, session_obj: Optional[requests.Session] = None) -> str:
    """请求页面并返回 HTML 文本"""
    headers = get_random_headers(referer=referer, is_ajax=is_ajax)
    
    # 添加随机延迟，避免请求过快
    time.sleep(random.uniform(0.5, 1.5))
    
    # 使用传入的 session 或全局 session
    sess = session_obj if session_obj else session
    
    logger.info(f"[GET] {url}")
    resp = sess.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    
    # 如果是 AJAX 请求，返回的内容可能是 JSON 格式的 HTML 字符串
    if is_ajax and resp.headers.get("Content-Type", "").startswith("application/json"):
        try:
            import json
            data = json.loads(resp.text)
            # 如果返回的是包含 HTML 的 JSON，提取 HTML 部分
            if isinstance(data, dict) and "html" in data:
                return data["html"]
            elif isinstance(data, str):
                # JSON 字符串格式的 HTML
                return data
        except:
            # 如果不是 JSON，直接返回文本
            pass
    
    return resp.text


def get_total_pages(base_url: str, session_obj: Optional[requests.Session] = None) -> int:
    """获取总页数"""
    try:
        # 先请求第一页
        html = fetch(f"{base_url}&p=1", referer=ALL_URL, is_ajax=True, session_obj=session_obj)
        
        # 检查是否被重定向
        if len(html) < 200 and "refresh" in html.lower():
            logger.warning(f"页面可能被重定向，HTML长度: {len(html)}")
            return 0
        
        soup = BeautifulSoup(html, "html.parser")
        
        # 检查是否有壁纸项
        list_items = soup.select(".list-item[data-key]")
        if not list_items:
            logger.warning("第一页没有找到壁纸项")
            return 0
        
        logger.info(f"第一页找到 {len(list_items)} 个壁纸组")
        
        # 查找分页组件 paging-box cross-center main-center
        paging_box = soup.select_one(".paging-box.cross-center.main-center")
        if paging_box:
            max_page = 0
            
            # 方法1: 从按钮的 data-max 属性获取总页数（最直接）
            jump_button = paging_box.select_one("button.paging-btn[data-max]")
            if jump_button:
                try:
                    max_page = int(jump_button.get("data-max", "0"))
                    if max_page > 0:
                        logger.info(f"从分页按钮 data-max 属性解析到总页数: {max_page}")
                        return max_page
                except (ValueError, AttributeError):
                    logger.info("方法1失败，使用兜底方案：尝试从页码链接的 data-key 属性提取")
            
            # 方法2: 从所有页码链接的 data-key 属性中提取最大值
            if max_page == 0:
                logger.info("方法1未找到总页数，使用兜底方案：从页码链接的 data-key 属性提取")
            page_links = paging_box.select("a.paging-link[data-key]")
            for link in page_links:
                try:
                    data_key = link.get("data-key", "")
                    if data_key.isdigit():
                        page_num = int(data_key)
                        max_page = max(max_page, page_num)
                except (ValueError, AttributeError):
                    continue
            
            # 方法3: 从链接文本中提取页码（备用方案）
            if max_page == 0:
                logger.info("方法1和方法2未找到总页数，使用兜底方案：从链接文本中提取页码")
                page_links = paging_box.select("a.paging-link")
                for link in page_links:
                    try:
                        page_text = link.get_text(strip=True)
                        if page_text.isdigit():
                            page_num = int(page_text)
                            max_page = max(max_page, page_num)
                    except (ValueError, AttributeError):
                        continue
            
            if max_page > 0:
                logger.info(f"从分页链接解析到总页数: {max_page}")
                return max_page
            else:
                logger.warning("分页组件存在但无法解析总页数，将使用默认值100")
        else:
            logger.warning("未找到分页组件 .paging-box.cross-center.main-center，将使用默认值100")
        
        # 如果无法解析，使用默认值100（向后兼容）
        max_pages = 100
        logger.info(f"将尝试最多 {max_pages} 页（如果某页没有数据会自动停止）")
        return max_pages
        
    except Exception as e:
        logger.error(f"获取总页数失败: {e}", exc_info=True)
        return 0


def parse_wallpaper_items(soup: BeautifulSoup, device_type: str = "电脑") -> List[Dict]:
    """解析每页的壁纸列表，从 download-pop 中获取支持的分辨率"""
    wallpapers = []
    
    # 遍历所有 .list-item 元素
    list_items = soup.select(".list-item")
    
    if not list_items:
        # parse_wallpaper_items 在 get_wallpapers_in_page 中调用，已在多线程环境中
        # 但这里暂时不添加锁，因为调用它的地方已经有锁了
        return []
    
    # 不在 parse_wallpaper_items 中打印，由调用者打印
    
    # 设备类型对应的尺寸优先级（从高到低）
    device_size_priority = {
        "电脑": [13, 12, 4, 3, 2, 1],  # 4K > 2K > 1080p > 其他
        "手机": [11, 7, 6],  # 最高分辨率优先
        "月历": [8, 9],  # 最高分辨率优先
        "4K": [13, 12, 4],  # 4K优先
        "平板": [8, 9],  # 最高分辨率优先
    }
    
    priority_sizes = device_size_priority.get(device_type, device_size_priority["电脑"])
    
    for list_item in list_items:
        # 1. 获取壁纸名称（从 .txt 元素）
        txt_elem = list_item.select_one(".txt")
        name = txt_elem.get_text(strip=True) if txt_elem else ""
        
        # 2. 获取 primaryid（从 download-pop 或 icon 元素）
        download_pop = list_item.select_one(".download-pop[primaryid]")
        if download_pop:
            primaryid = download_pop.get("primaryid", "")
        else:
            # 备用方法：从 icon 元素获取
            icon_elem = list_item.select_one(".icon[primaryid]")
            primaryid = icon_elem.get("primaryid", "") if icon_elem else ""
            if primaryid:
                logger.warning(f"壁纸项未找到 download-pop 元素，使用兜底方案：从 icon 元素获取 primaryid={primaryid}")
        
        if not primaryid:
            logger.warning(f"壁纸项无法获取 primaryid，跳过此项（名称: {name[:30] if name else '未命名'}）")
            continue
        
        # 3. 获取图片URL并提取日期信息（年/月）
        # 图片URL在 .item-a img[src] 中
        item_a = list_item.select_one(".item-a")
        img_elem = None
        image_url = ""
        year = ""
        month = ""
        
        if item_a:
            img_elem = item_a.select_one("img[src]")
        
        if img_elem:
            image_url = img_elem.get("src", "")
            # 格式1：/Uploads/image/2026/01/28/...
            date_match = re.search(r'/Uploads/image/(\d{4})/(\d{2})/', image_url)
            if date_match:
                year = date_match.group(1)  # 2026
                month = date_match.group(2)  # 01
            else:
                # 格式2：https://taociguan.dpm.org.cn/images/zjcphoto/2025-12-26/...
                date_match = re.search(r'/zjcphoto/(\d{4})-(\d{2})-', image_url)
                if date_match:
                    year = date_match.group(1)  # 2025
                    month = date_match.group(2)  # 12
                else:
                    # 格式3：尝试其他可能的日期格式
                    date_match = re.search(r'/(\d{4})/(\d{2})/', image_url)
                    if date_match:
                        year = date_match.group(1)
                        month = date_match.group(2)
        
        # 如果无法从图片URL提取日期
        if not year or not month:
            # 如果 primaryid 以 2 开头，归档到"更早"文件夹
            if primaryid.startswith("2"):
                year = "更早"
                month = ""
                logger.warning(f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) 无法从URL提取日期，primaryid以2开头，使用兜底方案：归档到'更早'文件夹")
            else:
                # 否则使用当前日期作为默认值
                current_time = time.localtime()
                year = str(current_time.tm_year)
                month = f"{current_time.tm_mon:02d}"
                logger.warning(f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) 无法从URL提取日期 ({image_url[:60] if image_url else '无URL'}...)，使用兜底方案：当前日期 {year}/{month}")
            # 注意：这里不使用 print_lock，因为 parse_wallpaper_items 不在多线程中调用
            # 如果后续改为多线程解析，需要添加锁
            # if image_url:
            #     print(f"[WARN] 壁纸 {primaryid} 无法从URL提取日期 ({image_url[:60]}...)，使用当前日期: {year}/{month}")
            # else:
            #     print(f"[WARN] 壁纸 {primaryid} 未找到图片URL，使用当前日期: {year}/{month}")
        
        # 3. 从 download-pop 中解析支持的分辨率
        available_sizes = {}
        if download_pop:
            # 查找所有 data-size 属性
            size_links = download_pop.select("a[data-size]")
            for link in size_links:
                try:
                    size_num = int(link.get("data-size", ""))
                    size_text = link.get_text(strip=True)  # 例如 "1920 x 1080"
                    if size_num and size_text:
                        available_sizes[size_num] = size_text
                except ValueError:
                    continue
        else:
            logger.warning(f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) 未找到 download-pop 元素，无法解析可用分辨率")
        
        # 4. 根据设备类型和可用分辨率，选择最高画质
        selected_size = None
        selected_px = None
        
        # 按优先级查找可用的最高分辨率
        for size_num in priority_sizes:
            if size_num in available_sizes:
                selected_size = size_num
                selected_px = available_sizes[size_num]
                break
        
        # 如果没有找到匹配的，使用可用分辨率中最大的
        if not selected_size and available_sizes:
            selected_size = max(available_sizes.keys())
            selected_px = available_sizes[selected_size]
            priority_str = ", ".join([str(s) for s in priority_sizes])
            available_sizes_str = ", ".join([f"{k}:{v}" for k, v in available_sizes.items()])
            logger.warning(f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) 未匹配到设备类型 '{device_type}' 的推荐分辨率优先级 [{priority_str}]，使用兜底方案：可用分辨率中的最大值 {selected_px} (可用: [{available_sizes_str}])")
        
        # 如果还是没有找到，使用默认值
        if not selected_size:
            # 使用设备类型的默认最高分辨率
            default_map = {
                "电脑": (13, "4000 x 2250"),
                "手机": (11, "1284 x 2778"),
                "月历": (8, "2732 x 2732"),
                "4K": (13, "4000 x 2250"),
                "平板": (8, "2732 x 2732"),
            }
            selected_size, selected_px = default_map.get(device_type, (13, "4000 x 2250"))
            available_sizes_str = ", ".join([f"{k}:{v}" for k, v in available_sizes.items()]) if available_sizes else "无"
            logger.warning(f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) 未匹配到设备类型 '{device_type}' 的推荐分辨率，可用分辨率: [{available_sizes_str}]，使用兜底方案：默认分辨率 {selected_px}")
            # 注意：这里不使用 print_lock，因为 parse_wallpaper_items 不在多线程中调用
            # 如果后续改为多线程解析，需要添加锁
        
        # 5. 构建下载URL
        download_url = IMG_DOWNLOAD_URL_TEMPLATE.format(
            primaryid=primaryid, size=selected_size
        )
        
        # 6. 如果没有名称，使用 primaryid
        if not name:
            name = f"wallpaper_{primaryid}"
            logger.warning(f"壁纸 {primaryid} 未找到名称，使用兜底方案：wallpaper_{primaryid}")
        
        wallpapers.append({
            "primaryid": primaryid,
            "name": name,
            "px": selected_px,
            "size": selected_size,
            "download_url": download_url,
            "year": year,
            "month": month,
        })
    
    return wallpapers


def download_wallpaper(
    url: str, 
    name: str, 
    px: str, 
    page_num: int, 
    index: int,
    device_folder: str,
    primaryid: str,
    year: str = "",
    month: str = "",
    session_obj: Optional[requests.Session] = None
):
    """下载单张壁纸
    
    文件夹结构：设备类型/年/月/ 或 设备类型/更早/
    文件名格式：文件编码_文件名_分辨率.png
    使用 primaryid 作为文件编码，确保即使文件名相同也不会覆盖
    """
    device = device_folder or "未知设备"
    px_norm = normalize_px(px)

    # 构建保存路径：设备类型/年/月/ 或 设备类型/更早/
    if year == "更早":
        # primaryid 以 2 开头且没有时间信息，归档到"更早"文件夹
        folder = os.path.join(DOWNLOAD_DIR, device_folder, "更早")
    elif year and month:
        folder = os.path.join(DOWNLOAD_DIR, device_folder, year, month)
    else:
        # 如果没有日期信息，使用设备类型文件夹
        folder = os.path.join(DOWNLOAD_DIR, device_folder)
        logger.warning(
            f"壁纸 {primaryid} ({name[:30] if name else '未命名'}) "
            f"没有日期信息（year={year}, month={month}），使用兜底方案：保存到设备类型文件夹 {device_folder}"
        )
    os.makedirs(folder, exist_ok=True)
    
    # 构建文件名：文件编码_文件名_分辨率.png
    safe_name = safe_segment(name) if name else f"wallpaper_{page_num}_{index}"
    # 分辨率字符串与文件名/数据库保持一致，例如 "1920 x 1080" -> "1920x1080"
    safe_px = px_norm
    # 再次确保没有其他特殊字符（理论上不会出现，但保留防御）
    safe_px = re.sub(r'[\\/:*?"<>|]', '_', safe_px)
    
    # 文件名格式：primaryid_文件名_分辨率.png
    filename = f"{primaryid}_{safe_name}_{safe_px}.png"
    filepath = os.path.join(folder, filename)

    # 计算数据库中使用的相对路径（相对于项目根目录）
    rel_path = os.path.relpath(filepath, pathlib.Path(".").resolve())

    # 先根据数据库判断是否已经下载过
    if db_has_wallpaper(primaryid=primaryid, px=px_norm, device=device):
        logger.info(
            f"[DB-SKIP] 壁纸 {primaryid} ({name[:30] if name else '未命名'}) "
            f"{px_norm} 已在数据库记录中，跳过下载"
        )
        return

    # 如果数据库没有记录，但文件已经存在，则认为是“历史文件”，补一条记录后跳过下载
    if os.path.exists(filepath):
        logger.info(
            f"[FS-SKIP] 壁纸 {primaryid} ({name[:30] if name else '未命名'}) "
            f"{px_norm} 文件已存在但数据库无记录，补充入库并跳过下载"
        )
        db_upsert_wallpaper(
            primaryid=primaryid,
            device=device,
            year=year,
            month=month,
            name=name,
            px=px_norm,
            rel_path=rel_path,
        )
        return
    
    logger.info(f"[DOWN] {filename} <- {url}")
    headers = get_random_headers(referer=ALL_URL, is_ajax=False)
    # 下载图片时添加额外的请求头
    headers.update({
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    })
    
    # 添加随机延迟
    time.sleep(random.uniform(0.3, 0.8))
    
    # 使用传入的 session 或全局 session
    sess = session_obj if session_obj else session
    
    try:
        with sess.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        # 下载成功后，写入数据库
        db_upsert_wallpaper(
            primaryid=primaryid,
            device=device,
            year=year,
            month=month,
            name=name,
            px=px_norm,
            rel_path=rel_path,
        )

        logger.info(f"[OK] {filename}")
    except Exception as e:
        logger.error(f"下载失败 {filename}: {e}", exc_info=True)


def get_wallpapers_in_page(
    base_url: str,
    page_num: int,
    device_folder: str,
    device_type: str = "电脑",
    session_obj: Optional[requests.Session] = None,
    thread_id: int = 0,
    device_label: Optional[str] = None,
) -> tuple[bool, bool]:
    """获取并下载每页的壁纸

    返回:
        (has_data, has_new)
        - has_data: 该页是否有壁纸数据
        - has_new:  该页是否至少包含一条数据库中尚不存在的壁纸
    """
    logger.info(f"=====>>> 当前页: {page_num}")
    
    # 添加页码参数
    url = f"{base_url}&p={page_num}"
    logger.info(f"=====>>> 当前页URL: {url}")
    html = fetch(url, referer=ALL_URL, is_ajax=True, session_obj=session_obj)
    
    # 检查是否返回空结果
    if len(html) < 200 and ("refresh" in html.lower() or not html.strip()):
        logger.info(f"第 {page_num} 页没有数据，停止爬取")
        return False, False
    
    soup = BeautifulSoup(html, "html.parser")
    
    wallpapers = parse_wallpaper_items(soup, device_type=device_type)
    logger.info(f"本页找到 {len(wallpapers)} 张壁纸")
    
    if len(wallpapers) == 0:
        logger.info(f"第 {page_num} 页没有壁纸，停止爬取")
        return False, False

    # 判断该页是否存在“数据库中尚不存在”的新壁纸
    label = device_label or (device_folder or "未知设备")
    has_new = False
    for wp in wallpapers:
        if not db_has_wallpaper(
            primaryid=wp["primaryid"],
            px=wp["px"],
            device=label,
        ):
            has_new = True
            break
    
    for index, wp in enumerate(wallpapers):
        download_wallpaper(
            url=wp["download_url"],
            name=wp["name"],
            px=wp["px"],
            page_num=page_num,
            index=index,
            device_folder=device_folder,
            primaryid=wp["primaryid"],
            year=wp.get("year", ""),
            month=wp.get("month", ""),
            session_obj=session_obj,
        )
        time.sleep(REQUEST_INTERVAL * 0.5)  # 下载间隔稍短
    
    return True, has_new


def download_pages_range(
    base_url: str,
    start_page: int,
    end_page: int,
    device_folder: str,
    device_type: str,
    thread_id: int
):
    """线程工作函数：下载指定范围的页面"""
    # 设置线程名称
    threading.current_thread().name = f"线程{thread_id}"
    
    # 每个线程创建独立的 Session
    thread_session = requests.Session()
    
    # 先访问主页面建立会话
    try:
        fetch(ALL_URL, session_obj=thread_session)
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"访问主页面失败: {e}")
    
    logger.info(f"开始下载页面范围: {start_page} - {end_page}")
    
    for page_num in range(start_page, end_page + 1):
        has_data, _ = get_wallpapers_in_page(
            base_url,
            page_num,
            device_folder,
            device_type,
            session_obj=thread_session,
            thread_id=thread_id,
            device_label=device_type or device_folder,
        )
        if not has_data:
            logger.info(f"第 {page_num} 页没有数据，停止爬取")
            break
        time.sleep(REQUEST_INTERVAL)
    
    logger.info(f"完成页面范围: {start_page} - {end_page}")


def crawl_by_device_type(
    category_id: Optional[int] = None,
    is_pc: int = 0,
    is_wap: int = 0,
    is_calendar: int = 0,
    is_four_k: int = 0,
    title: str = "",
    device_name: str = "全部",
    full_scan: bool = False,
):
    """按设备类型爬取壁纸

    参数:
    - full_scan: 如果为 True，则强制全量扫描所有页；
                 如果为 False，则先只看第一页：
                     若第一页所有壁纸都已在数据库中，则认为没有新内容，直接结束该设备类型的任务。
    """
    # 先访问主页面建立会话
    logger.info("访问主页面建立会话...")
    try:
        fetch(ALL_URL)
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"访问主页面失败: {e}")
    
    # 使用默认 category_id
    if category_id is None:
        category_id = DEFAULT_CATEGORY_ID
    
    # 构建基础参数（不包含页码）
    base_params = {
        "category_id": category_id,
        "pagesize": 24,
        "title": title,
        "is_pc": is_pc,
        "is_wap": is_wap,
        "is_calendar": is_calendar,
        "is_four_k": is_four_k,
    }
    
    # 构建基础URL（时间戳格式：0.xxx，作为第一个参数）
    timestamp = time.time() % 1  # 只取小数部分，格式为 0.xxx
    base_url = f"{FILTER_URL_TEMPLATE}?{timestamp}&{urlencode(base_params)}"

    # 设备文件夹名 / 设备标识（用于数据库 device 字段）
    device_folder = safe_segment(device_name) if device_name != "全部" else ""
    device_label = device_folder or "未知设备"

    # 获取总页数
    total_pages = get_total_pages(base_url)
    
    if total_pages == 0:
        logger.warning("未找到任何页面，请检查参数是否正确")
        return

    if not full_scan:
        # 增量模式：单线程顺序扫描，只要遇到一页全部在库，就停止后续扫描
        logger.info(
            f"增量模式：设备 {device_name} 将按页顺序扫描，"
            f"一旦遇到某一页所有壁纸都已在数据库中，则停止后续页面扫描。"
        )
        page_num = 1
        while page_num <= total_pages:
            has_data, has_new = get_wallpapers_in_page(
                base_url,
                page_num,
                device_folder,
                device_type=device_name,
                session_obj=None,
                thread_id=0,
                device_label=device_label,
            )
            if not has_data:
                logger.info(f"设备 {device_name} 第 {page_num} 页没有数据，停止扫描。")
                break
            if not has_new:
                logger.info(
                    f"设备 {device_name} 第 {page_num} 页所有壁纸都已在数据库中，"
                    f"根据增量规则，停止后续页面扫描。"
                )
                break
            page_num += 1
            time.sleep(REQUEST_INTERVAL)
        return

    # full_scan=True 时，仍然使用多线程全量下载
    logger.info(f"总页数: {total_pages}")
    logger.info(f"使用 {THREAD_COUNT} 个线程并发下载（full_scan 模式）")
    
    # 计算每个线程负责的页面范围
    pages_per_thread = total_pages // THREAD_COUNT
    remainder = total_pages % THREAD_COUNT
    
    threads = []
    start_page = 1
    
    for thread_id in range(THREAD_COUNT):
        # 分配页面范围
        end_page = start_page + pages_per_thread - 1
        if thread_id < remainder:  # 前 remainder 个线程多分配一页
            end_page += 1
        
        if start_page > total_pages:
            break
        
        # 创建线程
        thread = threading.Thread(
            target=download_pages_range,
            args=(base_url, start_page, end_page, device_folder, device_name, thread_id + 1)
        )
        thread.start()
        threads.append(thread)
        
        start_page = end_page + 1
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    logger.info("所有线程下载完成")


def crawl_all(
    category_id: Optional[int] = None,
    device_name: str = "全部",
    full_scan: bool = False,
):
    """爬取壁纸
    
    如果 device_name 为 "全部"，会按4种设备类型分别下载到4个不同的文件夹：
    - walls/电脑/
    - walls/手机/
    - walls/月历/
    - walls/4K/
    """
    logger.info("开始爬取壁纸...")
    logger.info(f"category_id: {category_id or DEFAULT_CATEGORY_ID}")
    logger.info(f"device_name: {device_name}")
    logger.info(f"full_scan: {full_scan}")
    
    # 定义所有设备类型
    all_device_types = ["电脑", "手机", "月历", "4K"]
    
    # 如果 device_name 是 "全部"，则下载所有4种设备类型
    if device_name == "全部":
        logger.info("="*60)
        logger.info("将按设备类型分别下载到4个不同的文件夹...")
        logger.info("文件夹结构：")
        for dt in all_device_types:
            folder_path = os.path.join(DOWNLOAD_DIR, safe_segment(dt))
            logger.info(f"  - {folder_path}/")
        logger.info("="*60)
        
        for idx, device_type in enumerate(all_device_types, 1):
            logger.info("="*60)
            logger.info(f"[{idx}/4] 开始下载 {device_type} 壁纸...")
            logger.info("="*60)
            
            # 根据设备名称设置对应的标志
            is_pc = 0
            is_wap = 0
            is_calendar = 0
            is_four_k = 0
            
            if device_type == "电脑":
                is_pc = 1
            elif device_type == "手机":
                is_wap = 1
            elif device_type == "月历":
                is_calendar = 1
            elif device_type == "4K":
                is_four_k = 1
            
            try:
                crawl_by_device_type(
                    category_id=category_id,
                    is_pc=is_pc,
                    is_wap=is_wap,
                    is_calendar=is_calendar,
                    is_four_k=is_four_k,
                    title="",
                    device_name=device_type,
                    full_scan=full_scan,
                )
                logger.info(f"✓ {device_type} 壁纸下载完成")
            except Exception as e:
                logger.error(f"✗ {device_type} 壁纸下载失败: {e}", exc_info=True)
            
            # 每个设备类型下载完成后稍作延迟（最后一个不需要延迟）
            if idx < len(all_device_types):
                logger.info("等待 2 秒后继续下一个设备类型...")
                time.sleep(2)
    else:
        # 单个设备类型下载
        if device_name not in all_device_types:
            logger.warning(f"未知的设备类型: {device_name}")
            logger.info(f"支持的设备类型: {', '.join(all_device_types)}")
            return
        
        logger.info(f"将下载到文件夹: {os.path.join(DOWNLOAD_DIR, safe_segment(device_name))}/")
        
        is_pc = 0
        is_wap = 0
        is_calendar = 0
        is_four_k = 0
        
        if device_name == "电脑":
            is_pc = 1
        elif device_name == "手机":
            is_wap = 1
        elif device_name == "月历":
            is_calendar = 1
        elif device_name == "4K":
            is_four_k = 1
        
        crawl_by_device_type(
            category_id=category_id,
            is_pc=is_pc,
            is_wap=is_wap,
            is_calendar=is_calendar,
            is_four_k=is_four_k,
            title="",
            device_name=device_name,
            full_scan=full_scan,
        )


if __name__ == "__main__":
    """
    注意：
    - 本脚本仅供个人学习与非商业用途，严格遵守故宫博物院壁纸栏目版权声明
    
    使用示例：
    # 爬取电脑壁纸
    python download_gugong_walls.py --device_name "电脑"
    
    # 爬取手机壁纸
    python download_gugong_walls.py --device_name "手机"
    
    # 爬取月历壁纸
    python download_gugong_walls.py --device_name "月历"
    
    # 爬取4K壁纸
    python download_gugong_walls.py --device_name "4K"
    
    # 爬取全部（默认，会按4种设备类型分别下载到4个文件夹）
    python download_gugong_walls.py
    
    # 或者明确指定
    python download_gugong_walls.py --device_name "全部"
    """
    import sys
    
    # 设置主线程名称为中文
    threading.current_thread().name = "主线程"
    
    # 解析命令行参数
    category_id = None
    device_name = "全部"
    full_scan = False
    
    # 简单的参数解析
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--category_id" and i + 1 < len(args):
            category_id = int(args[i + 1])
            i += 2
        elif args[i] == "--device_name" and i + 1 < len(args):
            device_name = args[i + 1]
            i += 2
        elif args[i] == "--full_scan":
            full_scan = True
            i += 1
        else:
            i += 1
    
    crawl_all(
        category_id=category_id,
        device_name=device_name,
        full_scan=full_scan,
    )
    
    logger.info("==== 完成 ====")
    logger.info(f"图片保存在: {pathlib.Path(DOWNLOAD_DIR).resolve()}")
    logger.info(f"日志文件保存在: {pathlib.Path(log_filename).resolve()}")
