# 故宫博物院壁纸下载工具

一个用于批量下载故宫博物院官方网站壁纸栏目的 Python 脚本。

## ⚠️ 重要声明

**本脚本仅供个人学习与非商业用途，严格遵守故宫博物院壁纸栏目版权声明：**

- 仅可将壁纸用于个人的非商业用途
- 使用时需明确标注内容出处为"故宫博物院壁纸栏目"
- 严禁将壁纸用于任何形式的商业用途（包括但不限于广告宣传、出版印刷、衍生商品开发等）
- 对于违反上述规则的行为，故宫博物院保留追究其法律责任的权利

## 功能特性

- ✅ 自动分页下载所有壁纸
- ✅ 按设备类型分类保存（电脑/手机/月历/4K）
- ✅ **按上传日期自动分类**：设备类型/年/月/文件夹结构，老历史图归入「更早」
- ✅ 智能选择最高画质分辨率（按设备类型的优先级自动挑选）
- ✅ 从页面解析每个壁纸实际支持的分辨率
- ✅ **文件名格式**：文件编码_文件名_分辨率.png（使用 `primaryid` 作为唯一标识，避免重名覆盖）
- ✅ 本地 **SQLite 数据库去重**：按 `(primaryid, 分辨率, 设备类型)` 去重，避免重复下载
- ✅ **增量扫描模式**：按页顺序扫描，只要遇到某一页全部在库，就停止后续扫描，减轻服务器压力
- ✅ 可选 **全量扫描模式**：使用多线程拉满所有页（`--full_scan`）
- ✅ 随机 User-Agent 和完整请求头模拟，降低请求失败率
- ✅ 错误处理和重试机制
- ✅ **日志持久化**：所有操作日志自动保存到 `logs/` 目录，方便追踪下载进度和排查问题
- ✅ **多线程并发下载**：在全量扫描模式下支持多线程并发下载

## 安装依赖

```bash
pip install requests beautifulsoup4
```

## 使用方法

### 基本用法

```bash
# 下载电脑壁纸（默认最高画质：4000x2250 4K）
python download_gugong_walls.py --device_name "电脑"

# 下载手机壁纸（默认最高画质：1284x2778）
python download_gugong_walls.py --device_name "手机"

# 下载月历壁纸（默认最高画质：2732x2732）
python download_gugong_walls.py --device_name "月历"

# 下载4K壁纸（默认最高画质：4000x2250）
python download_gugong_walls.py --device_name "4K"
```

### 参数说明

- `--device_name`: 设备类型（电脑/手机/月历/4K），默认 `"全部"`（四种设备依次下载）
- `--category_id`: 分类ID（可选，默认 624）
- `--full_scan`: 强制全量扫描所有页
  - 不加时（默认）：**增量模式**，只要遇到一页全部在数据库中，就停止后续页面扫描
  - 加上时：**全量模式**，使用多线程把所有页都扫完（更耗时、更压服务器）

## 下载步骤详解

### 1. 初始化阶段

```pseudocode
BEGIN
    创建全局 Session 对象（保持 cookies）
    解析命令行参数
        device_name ← 从命令行获取或使用默认值"全部"
        category_id ← 从命令行获取或使用默认值624
  
    根据 device_name 设置设备标志
        IF device_name == "电脑" THEN
            is_pc ← 1
            is_wap ← 0
            is_calendar ← 0
            is_four_k ← 0
        ELSE IF device_name == "手机" THEN
            is_pc ← 0
            is_wap ← 1
            is_calendar ← 0
            is_four_k ← 0
        // ... 其他设备类型类似
    END IF
END
```

### 2. 建立会话

```pseudocode
BEGIN
    访问主页面建立会话
        url ← "https://www.dpm.org.cn/lights/royal.html"
        headers ← {
            User-Agent: "Mozilla/5.0 ...",
            Accept: "text/html,application/xhtml+xml",
            Referer: url
        }
        response ← GET(url, headers=headers)
        保存 cookies 到 Session
    END
END
```

### 3. 构建搜索 URL

```pseudocode
BEGIN
    构建搜索参数
        params ← {
            category_id: 624,
            pagesize: 24,
            title: "",
            is_pc: is_pc,
            is_wap: is_wap,
            is_calendar: is_calendar,
            is_four_k: is_four_k
        }
  
    生成时间戳（避免缓存）
        timestamp ← time.time() % 1  // 格式：0.xxx
  
    构建基础 URL
        base_url ← "https://www.dpm.org.cn/searchs/royalb.html?" 
                    + timestamp + "&" + urlencode(params)
    END
END
```

### 4. 获取总页数

```pseudocode
FUNCTION get_total_pages(base_url)
BEGIN
    请求第一页（带 AJAX 头）
        url ← base_url + "&p=1"
        headers ← {
            Accept: "application/json, text/javascript, */*; q=0.01",
            X-Requested-With: "XMLHttpRequest",
            Referer: "https://www.dpm.org.cn/lights/royal.html"
        }
        response ← GET(url, headers=headers)
        html ← JSON.parse(response.text)  // 返回的是 JSON 格式的 HTML 字符串
  
    解析 HTML
        soup ← BeautifulSoup(html)
        list_items ← soup.select(".list-item[data-key]")
  
    IF list_items 不存在 THEN
        RETURN 0
    END IF
  
    查找分页组件
        paging_box ← soup.select_one(".paging-box.cross-center.main-center")
  
    IF paging_box 存在 THEN
        max_page ← 0
      
        // 方法1: 优先从按钮的 data-max 属性获取总页数（最直接）
        jump_button ← paging_box.select_one("button.paging-btn[data-max]")
        IF jump_button 存在 THEN
            max_page ← int(jump_button.get("data-max"))
            IF max_page > 0 THEN
                RETURN max_page
            END IF
        END IF
      
        // 方法2: 从所有页码链接的 data-key 属性中提取最大值
        page_links ← paging_box.select("a.paging-link[data-key]")
        FOR EACH link IN page_links DO
            data_key ← link.get("data-key")
            IF data_key 是数字 THEN
                page_num ← int(data_key)
                max_page ← max(max_page, page_num)
            END IF
        END FOR
      
        // 方法3: 从链接文本中提取页码（备用方案）
        IF max_page == 0 THEN
            page_links ← paging_box.select("a.paging-link")
            FOR EACH link IN page_links DO
                page_text ← link.get_text(strip=True)
                IF page_text 是数字 THEN
                    page_num ← int(page_text)
                    max_page ← max(max_page, page_num)
                END IF
            END FOR
        END IF
      
        IF max_page > 0 THEN
            RETURN max_page
        ELSE
            PRINT "分页组件存在但无法解析总页数，将使用默认值100"
            RETURN 100
        END IF
    ELSE
        PRINT "未找到分页组件，将使用默认值100"
        RETURN 100
    END IF
END FUNCTION
```

### 5. 增量扫描与全量扫描

```pseudocode
FUNCTION crawl_by_device_type(category_id, is_pc, is_wap, is_calendar, is_four_k, title, device_name, full_scan)
BEGIN
    构建搜索参数和 base_url 同上

    获取总页数
        total_pages ← get_total_pages(base_url)
  
    IF total_pages == 0 THEN
        PRINT "未找到任何页面"
        RETURN
    END IF

    IF full_scan == False THEN
        // 增量模式：单线程顺序扫描，只要有一页“全部在库”就停止
        page_num ← 1
        WHILE page_num ≤ total_pages DO
            (has_data, has_new) ← get_wallpapers_in_page(
                base_url, page_num, device_folder, device_type=device_name
            )

            IF has_data == False THEN
                PRINT "第 {page_num} 页没有数据，停止扫描"
                BREAK
            END IF

            IF has_new == False THEN
                PRINT "第 {page_num} 页所有壁纸均已在数据库中，停止后续页面扫描"
                BREAK
            END IF

            page_num ← page_num + 1
            SLEEP REQUEST_INTERVAL 秒
        END WHILE
    ELSE
        // 全量模式：多线程扫描所有页
        计算每个线程负责的页面范围
            pages_per_thread ← total_pages // THREAD_COUNT  // 例如：189 // 5 = 37
            remainder ← total_pages % THREAD_COUNT          // 例如：189 % 5 = 4
      
        创建并启动线程
            start_page ← 1
            FOR thread_id FROM 1 TO THREAD_COUNT DO
                // 分配页面范围
                end_page ← start_page + pages_per_thread - 1
                IF thread_id <= remainder THEN  // 前 remainder 个线程多分配一页
                    end_page ← end_page + 1
                END IF

                IF start_page > total_pages THEN
                    BREAK
                END IF
              
                // 创建线程，负责下载 start_page 到 end_page 的页面
                thread ← CREATE_THREAD(
                    target=download_pages_range,
                    args=(base_url, start_page, end_page, device_folder, device_type, thread_id)
                )
                thread.start()
              
                start_page ← end_page + 1
            END FOR
      
        等待所有线程完成
            FOR EACH thread IN threads DO
                thread.join()
            END FOR
    END IF
END FUNCTION
```

### 6. 线程工作函数：下载指定范围的页面（仅 full_scan 模式使用）

```pseudocode
FUNCTION download_pages_range(base_url, start_page, end_page, device_folder, device_type, thread_id)
BEGIN
    设置线程名称
        current_thread.name ← "线程" + thread_id
  
    创建独立的 Session
        thread_session ← requests.Session()
  
    访问主页面建立会话
        fetch(ALL_URL, session_obj=thread_session)
  
    FOR page_num FROM start_page TO end_page DO
        has_data ← get_wallpapers_in_page(
            base_url, page_num, device_folder, device_type, 
            session_obj=thread_session, thread_id=thread_id
        )
      
        IF has_data == False THEN
            PRINT "第 {page_num} 页没有数据，停止爬取"
            BREAK
        END IF
      
        SLEEP 1秒  // 页面间隔
    END FOR
END FUNCTION
```

### 7. 遍历每一页

```pseudocode
FUNCTION get_wallpapers_in_page(base_url, page_num, device_folder, device_type, session_obj, thread_id)
BEGIN
    请求当前页数据
        url ← base_url + "&p=" + page_num
        html ← fetch(url, referer=ALL_URL, is_ajax=True, session_obj=session_obj)
      
        IF html 长度 < 200 OR 包含 "refresh" THEN
            RETURN (False, False)
        END IF
  
    解析壁纸列表（从 HTML 中提取每个壁纸的 primaryid、名称、分辨率、日期等）
        soup ← BeautifulSoup(html)
        wallpapers ← parse_wallpaper_items(soup, device_type)
      
        IF wallpapers 为空 THEN
            RETURN (False, False)
        END IF
  
    // 判断本页是否存在数据库中尚不存在的新壁纸
    has_new ← False
    FOR EACH wallpaper IN wallpapers DO
        IF NOT db_has_wallpaper(wallpaper.primaryid, wallpaper.px, device_label) THEN
            has_new ← True
            BREAK
        END IF
    END FOR

    // 下载每张壁纸（内部会再次基于数据库做精确去重）
    FOR EACH wallpaper IN wallpapers DO
        download_wallpaper(
            url=wallpaper.download_url,
            name=wallpaper.name,
            px=wallpaper.px,
            device_folder=device_folder,
            primaryid=wallpaper.primaryid,
            year=wallpaper.year,
            month=wallpaper.month,
            session_obj=session_obj
        )
        SLEEP 0.5秒  // 下载间隔
    END FOR
  
    RETURN (True, has_new)
END FUNCTION
```

### 8. 解析壁纸列表

```pseudocode
FUNCTION parse_wallpaper_items(soup, device_type)
BEGIN
    wallpapers ← []
    list_items ← soup.select(".list-item")
  
    // 设备类型对应的尺寸优先级（从高到低）
    device_size_priority ← {
        "电脑": [13, 12, 4, 3, 2, 1],  // 4K > 2K > 1080p > 其他
        "手机": [11, 7, 6],
        "月历": [8, 9],
        "4K": [13, 12, 4],
    }
    priority_sizes ← device_size_priority[device_type]
  
    FOR EACH list_item IN list_items DO
    BEGIN
        // 1. 获取壁纸名称
        txt_elem ← list_item.select_one(".txt")
        name ← txt_elem.get_text(strip=True) IF txt_elem EXISTS ELSE ""
  
        // 2. 获取 primaryid
        download_pop ← list_item.select_one(".download-pop[primaryid]")
        IF download_pop EXISTS THEN
            primaryid ← download_pop.get("primaryid")
        ELSE
            icon_elem ← list_item.select_one(".icon[primaryid]")
            primaryid ← icon_elem.get("primaryid") IF icon_elem EXISTS ELSE ""
        END IF
  
        IF primaryid 为空 THEN
            CONTINUE  // 跳过此项
        END IF
  
        // 3. 从图片URL提取日期信息（年/月）
        img_elem ← list_item.select_one("img[src]")
        year ← ""
        month ← ""
  
        IF img_elem EXISTS THEN
            image_url ← img_elem.get("src")
            // 从URL提取日期：/Uploads/image/2026/01/28/...
            date_match ← REGEX_MATCH(image_url, "/Uploads/image/(\d{4})/(\d{2})/")
            IF date_match EXISTS THEN
                year ← date_match.group(1)  // 2026
                month ← date_match.group(2)  // 01
            END IF
        END IF
  
        // 如果无法提取日期，使用当前日期
        IF year 为空 OR month 为空 THEN
            current_time ← GET_CURRENT_TIME()
            year ← current_time.year
            month ← FORMAT(current_time.month, "02d")
        END IF
  
        // 4. 从 download-pop 中解析支持的分辨率
        available_sizes ← {}
        IF download_pop EXISTS THEN
            size_links ← download_pop.select("a[data-size]")
            FOR EACH link IN size_links DO
                size_num ← int(link.get("data-size"))
                size_text ← link.get_text(strip=True)  // 例如 "1920 x 1080"
                available_sizes[size_num] ← size_text
            END FOR
        END IF
  
        // 5. 根据设备类型和可用分辨率，选择最高画质
        selected_size ← NULL
        selected_px ← NULL
  
        // 按优先级查找可用的最高分辨率
        FOR EACH size_num IN priority_sizes DO
            IF size_num IN available_sizes THEN
                selected_size ← size_num
                selected_px ← available_sizes[size_num]
                BREAK
            END IF
        END FOR
  
        // 如果没有找到匹配的，使用可用分辨率中最大的
        IF selected_size == NULL AND available_sizes 不为空 THEN
            selected_size ← max(available_sizes.keys())
            selected_px ← available_sizes[selected_size]
        END IF
  
        // 如果还是没有找到，使用默认值
        IF selected_size == NULL THEN
            default_map ← {
                "电脑": (13, "4000 x 2250"),
                "手机": (11, "1284 x 2778"),
                "月历": (8, "2732 x 2732"),
                "4K": (13, "4000 x 2250"),
                "平板": (8, "2732 x 2732")
            }
            (selected_size, selected_px) ← default_map[device_type]
        END IF
  
        // 6. 构建下载URL
        download_url ← "https://www.dpm.org.cn/download/lights_image/id/"
                        + primaryid + "/img_size/" + selected_size + ".html"
  
        // 7. 如果没有名称，使用 primaryid
        IF name 为空 THEN
            name ← "wallpaper_" + primaryid
        END IF
  
        wallpapers.append({
            primaryid: primaryid,
            name: name,
            px: selected_px,
            size: selected_size,
            download_url: download_url,
            year: year,
            month: month
        })
    END FOR
  
    RETURN wallpapers
END FUNCTION
```

### 9. 下载单张壁纸

```pseudocode
FUNCTION download_wallpaper(url, name, px, page_num, index, device_folder, primaryid, year, month)
BEGIN
    // 构建保存路径：设备类型/年/月/
    IF year 不为空 AND month 不为空 THEN
        folder ← DOWNLOAD_DIR + "/" + device_folder + "/" + year + "/" + month
    ELSE
        folder ← DOWNLOAD_DIR + "/" + device_folder
    END IF
    CREATE_DIRECTORY(folder) IF NOT EXISTS
  
    // 构建文件名：文件编码_文件名_分辨率.png
    safe_name ← safe_segment(name)  // 处理特殊字符
    // 分辨率与数据库/文件名保持一致，例如 "1920 x 1080" -> "1920x1080"
    safe_px ← NORMALIZE_PX(px)
    filename ← primaryid + "_" + safe_name + "_" + safe_px + ".png"
    filepath ← folder + "/" + filename
  
    // 先基于数据库检查是否已存在记录（示意）
    IF db_has_wallpaper(primaryid, px, device) THEN
        PRINT "[DB-SKIP] {filename} 已在数据库中，跳过下载"
        RETURN
    END IF
  
    // 如果文件存在但数据库没有记录，则补一条记录后跳过下载
    IF filepath EXISTS AND NOT db_has_wallpaper(primaryid, px, device) THEN
        db_upsert_wallpaper(primaryid, device, year, month, name, px, rel_path)
        PRINT "[FS-SKIP] {filename} 文件已存在但数据库无记录，补充入库并跳过下载"
        RETURN
    END IF
  
    // 下载图片
    PRINT "[DOWN] {filename} <- {url}"
    headers ← {
        User-Agent: "Mozilla/5.0 ...",
        Referer: "https://www.dpm.org.cn/lights/royal.html"
    }
  
    TRY
        response ← GET(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
      
        WRITE response.content TO filepath
      
        // 下载成功后写入数据库
        db_upsert_wallpaper(primaryid, device, year, month, name, px, rel_path)
        PRINT "[OK] {filename}"
    CATCH Exception AS e
        PRINT "[ERROR] 下载失败 {filename}: {e}"
    END TRY
END FUNCTION
```

## 分辨率映射表

脚本支持以下分辨率格式：


| 尺寸编号 | 分辨率      | 设备类型 | 说明             |
| -------- | ----------- | -------- | ---------------- |
| 1        | 1920 x 1280 | 电脑     | 横版             |
| 2        | 1280 x 800  | 电脑     | 横版             |
| 3        | 1680 x 1050 | 电脑     | 横版             |
| 4        | 1920 x 1080 | 电脑     | 横版，1080p      |
| 6        | 1080 x 1920 | 手机     | 竖版             |
| 7        | 1125 x 2436 | 手机     | 竖版             |
| 8        | 2732 x 2732 | 平板     | 方形             |
| 9        | 2048 x 2048 | 平板     | 方形             |
| 11       | 1284 x 2778 | 手机     | 竖版，最高分辨率 |
| 12       | 2560 x 1440 | 电脑     | 横版，2K         |
| 13       | 4000 x 2250 | 电脑     | 横版，4K最高画质 |

## 日志功能

脚本会自动将所有的操作日志保存到 `logs/` 目录下，日志文件名格式为：

```
logs/download_YYYYMMDD_HHMMSS.log
```

**日志内容包括：**

- 下载进度信息（当前页、线程ID、下载状态）
- 文件下载成功/失败记录
- 错误信息和异常堆栈
- 线程执行情况

**日志格式：**

```
2026-02-10 14:30:25 [INFO] [主线程] 访问主页面建立会话...
2026-02-10 14:30:25 [INFO] [主线程] 从分页按钮 data-max 属性解析到总页数: 189
2026-02-10 14:30:25 [INFO] [主线程] 总页数: 189
2026-02-10 14:30:25 [INFO] [主线程] 使用 5 个线程并发下载
2026-02-10 14:30:26 [INFO] [线程1] 开始下载页面范围: 1 - 38
2026-02-10 14:30:26 [INFO] [线程2] 开始下载页面范围: 39 - 76
2026-02-10 14:30:26 [INFO] [线程1] =====>>> 当前页: 1
2026-02-10 14:30:27 [INFO] [线程1] 本页找到 24 张壁纸
2026-02-10 14:30:28 [INFO] [线程1] [DOWN] 3****0_清***杯_2560x1440.png <- https://...
2026-02-10 14:30:30 [INFO] [线程1] [OK] 3****0_清***杯_2560x1440.png
```

**查看日志：**

```bash
# Windows PowerShell
Get-Content logs\download_*.log -Tail 50

# Linux/Mac
tail -f logs/download_*.log
```

## 目录结构

下载后的文件会按以下结构保存（按设备类型和上传日期分类）：

```
项目根目录/
├── walls/                    # 下载的壁纸目录
│   ├── 电脑/
│   │   ├── 2026/
│   │   │   ├── 01/
│   │   │   │   ├── 3****7_清***册_4000x2250.png
│   │   │   │   ├── 3****0_清***马_4000x2250.png
│   │   │   │   └── ...
│   │   │   └── 02/
│   │   │       └── ...
│   │   └── 2025/
│   │       └── 12/
│   │           └── ...
│   ├── 手机/
│   │   ├── 2026/
│   │   │   └── 01/
│   │   │       ├── 3****7_清***册_1284x2778.png
│   │   │       └── ...
│   │   └── ...
│   ├── 月历/
│   │   ├── 2026/
│   │   │   └── 01/
│   │   │       └── ...
│   │   └── ...
│   └── 4K/
│       └── ...
├── logs/                     # 日志目录
│   ├── download_20***0_1*5.log
│   ├── download_20***0_1*0.log
│   └── ...
└── download_gugong_walls.py  # 主脚本
```

**文件夹结构说明：**

- 第一层：设备类型（电脑/手机/月历/4K）
- 第二层：年份（如 2026）
- 第三层：月份（如 01、02）
- 文件名格式：`文件编码_文件名_分辨率.png`

## 关键特性说明

### 1. 智能分辨率选择

脚本会：

1. 从每个壁纸的 `download-pop` 元素中解析实际支持的分辨率
2. 根据设备类型，按优先级选择最高画质
3. 如果某个分辨率不支持，自动降级到次高分辨率

### 2. 文件名处理

- **文件名格式**：`文件编码_文件名_分辨率.png`
  - 文件编码：使用 `primaryid` 作为唯一标识，确保即使文件名相同也不会覆盖
  - 文件名：使用壁纸的实际名称（从 `.txt` 元素获取）
  - 分辨率：自动处理格式，如 `4000x2250`
- 自动处理文件名中的特殊字符（Windows 不允许的字符会被替换为下划线）
- 示例：`378377_清 汪承霈熙春呈秀图册_4000x2250.png`

### 3. 按日期自动分类

- 从图片URL中提取上传日期（年/月）
- URL格式：`/Uploads/image/2026/01/28/...`
- 自动创建对应的年/月文件夹
- 如果无法提取日期，使用当前日期作为默认值
- 便于按时间查找和管理壁纸

### 4. 错误处理

- 网络错误时自动跳过，继续下载下一张
- 文件已存在时自动跳过
- 页面为空时自动停止爬取

### 5. 多线程并发下载

- 默认使用 5 个线程并发下载
- **从分页组件实际解析总页数**，然后平均分配给各个线程
- 每个线程独立维护 Session，避免冲突
- 线程安全的日志输出，确保日志信息清晰可读
- 例如：如果总页数是 189 页，5 个线程分别负责：
  - 线程1: 1-38 页
  - 线程2: 39-76 页
  - 线程3: 77-114 页
  - 线程4: 115-152 页
  - 线程5: 153-189 页

### 6. 日志持久化

- 所有操作日志自动保存到 `logs/` 目录
- 日志文件按时间戳命名，方便追踪每次运行
- 同时输出到控制台和文件，方便实时查看和历史追溯
- 包含线程ID信息，便于多线程环境下的问题排查

### 7. 礼貌访问

- 页面请求间隔：1秒
- 图片下载间隔：0.5秒
- 随机延迟：0.3-0.8秒（避免请求过于规律）
- 避免对服务器造成过大压力

## 注意事项

1. **版权声明**：请严格遵守故宫博物院的版权声明，仅用于个人非商业用途
2. **网络环境**：需要能够访问 `www.dpm.org.cn` 域名
3. **存储空间**：4K 壁纸文件较大，请确保有足够的存储空间
4. **下载时间**：根据壁纸数量，完整下载可能需要较长时间

## 常见问题

### Q: 下载失败怎么办？

A: 脚本会自动跳过失败的图片，继续下载其他图片。可以重新运行脚本，已下载的文件会自动跳过。

### Q: 如何修改下载的分辨率？

A: 修改脚本中的 `device_size_priority` 字典，调整优先级顺序即可。

### Q: 可以同时下载多个设备类型吗？

A: 可以，分别运行不同的命令即可。例如：

```bash
python download_gugong_walls.py --device_name "电脑" &
python download_gugong_walls.py --device_name "手机" &
```

## 技术实现

- **语言**：Python 3.7+
- **依赖库**：
  - `requests`：HTTP 请求
  - `beautifulsoup4`：HTML 解析
- **请求方式**：使用 Session 保持 cookies，模拟浏览器行为
- **数据格式**：网站返回 JSON 格式的 HTML 字符串

## 更新日志

- **v1.0**：初始版本，支持基本下载功能
- **v1.1**：添加从 `download-pop` 解析实际支持的分辨率
- **v1.2**：使用壁纸名称作为文件名
- **v1.3**：智能选择最高画质分辨率
- **v1.4**：
  - 文件名格式改为：`文件编码_文件名_分辨率.png`（使用 primaryid 作为唯一标识）
  - 添加按上传日期自动分类：`设备类型/年/月/` 文件夹结构
  - 从图片URL提取日期信息
  - 添加随机 User-Agent 和完整请求头模拟
- **v1.5**：
  - 实现多线程并发下载，大幅提升下载速度
  - 添加日志持久化功能，所有操作日志保存到 `logs/` 目录
  - 优化线程管理，每个线程独立 Session，避免冲突
  - 改进日志格式，包含线程ID和时间戳信息
- **v1.6**：
  - 从分页组件 `.paging-box.cross-center.main-center` 中实际解析总页数
  - 优先从按钮的 `data-max` 属性获取总页数
  - 支持从页码链接的 `data-key` 属性提取总页数

## 许可证

本脚本仅供学习和个人使用，请遵守故宫博物院的版权声明。

## 参考链接

- [故宫博物院壁纸栏目](https://www.dpm.org.cn/lights/royal.html)
- [版权声明](https://www.dpm.org.cn/lights/royal.html)
