# 立创·庐山派-K230-CanMV开发板资料与相关扩展板软硬件资料官网全部开源
# 开发板官网：www.lckfb.com
# 技术支持常驻论坛，任何技术问题欢迎随时交流学习
# 立创论坛：www.jlc-bbs.com/lckfb
# 关注bilibili账号：【立创开发板】，掌握我们的最新动态！
# 不靠卖板赚钱，以培养中国工程师为己任

import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

# 设置合适的分辨率，考虑性能和识别效果的平衡
# 320x240为低分辨率，性能好但识别可能不太稳定
# 640x480为高分辨率，识别好但可能影响性能
# 480x320为中等分辨率，平衡性能和识别效果
picture_width = 480
picture_height = 320

# 帧率计数器
fps_count = 0
last_time = time.ticks_ms()

sensor_id = 2
sensor = None

# 显示模式选择：可以是 "VIRT"、"LCD" 或 "HDMI"
DISPLAY_MODE = "LCD"

# 根据模式设置显示宽高
if DISPLAY_MODE == "VIRT":
    # 虚拟显示器模式
    DISPLAY_WIDTH = ALIGN_UP(1920, 16)
    DISPLAY_HEIGHT = 1080
elif DISPLAY_MODE == "LCD":
    # 3.1寸屏幕模式
    DISPLAY_WIDTH = 800
    DISPLAY_HEIGHT = 480
elif DISPLAY_MODE == "HDMI":
    # HDMI扩展板模式
    DISPLAY_WIDTH = 1920
    DISPLAY_HEIGHT = 1080
else:
    raise ValueError("未知的 DISPLAY_MODE，请选择 'VIRT', 'LCD' 或 'HDMI'")

try:
    # 构造一个具有默认配置的摄像头对象
    sensor = Sensor(id=sensor_id)
    # 重置摄像头sensor
    sensor.reset()

    # 无需进行镜像翻转
    # 设置水平镜像
    # sensor.set_hmirror(False)
    # 设置垂直翻转
    # sensor.set_vflip(False)

    # 设置通道0的输出尺寸
    sensor.set_framesize(width=picture_width, height=picture_height, chn=CAM_CHN_ID_0)
    # 设置通道0的输出像素格式为RGB565
    sensor.set_pixformat(Sensor.RGB565, chn=CAM_CHN_ID_0)

    # 根据模式初始化显示器
    if DISPLAY_MODE == "VIRT":
        Display.init(Display.VIRT, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, fps=60)
    elif DISPLAY_MODE == "LCD":
        Display.init(Display.ST7701, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)
    elif DISPLAY_MODE == "HDMI":
        Display.init(Display.LT9611, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)

    # 初始化媒体管理器
    MediaManager.init()
    # 启动传感器
    sensor.run()

    # 定义黑色阈值
    black_threshold = [(0, 42)]  # 亮度低于42认为是黑色

    # 最小矩形面积（根据分辨率调整）
    min_rect_area = int(picture_width * picture_height * 0.002)  # 自适应最小面积
    
    # 最大矩形面积（过滤过大的区域）
    max_rect_area = picture_width * picture_height * 0.9
    
    # 存储上一帧的大矩形
    prev_large_rect = None
    
    # 平滑因子（值越大越平滑，范围0-1）
    smooth_factor = 0.6
    
    # 存储上一帧检测到的内部矩形（按网格位置）
    prev_inner_grid = {i: None for i in range(1, 10)}
    
    # 内部矩形的历史有效帧计数
    inner_valid_frames = {i: 0 for i in range(1, 10)}
    
    # 历史帧数阈值（多少帧检测到才认为稳定）
    valid_frames_threshold = 2
    
    # 性能模式标志（True为高性能模式，牺牲一些精度）
    high_perf_mode = True

    while True:
        os.exitpoint()

        # 捕获通道0的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)
        
        # 帧率计数
        fps_count += 1
        if time.ticks_ms() - last_time >= 1000:
            # 显示帧率
            fps = fps_count
            print(f"FPS: {fps}")
            fps_count = 0
            last_time = time.ticks_ms()
        
        # 创建图像副本用于处理（高性能模式下可以直接处理原图）
        if high_perf_mode:
            img_processed = img
        else:
            img_processed = img.copy()
        
        # 降噪处理（高性能模式下减少处理）
        if not high_perf_mode:
            img_processed = img_processed.bilateral(1, color_sigma=0.1, space_sigma=1)
        
        # 对图像进行二值化处理，提取黑色区域
        img_binary = img_processed.binary(black_threshold, invert=False)
        
        # 进行形态学操作，去除噪点
        if high_perf_mode:
            # 高性能模式下简化形态学操作
            img_binary = img_binary.dilate(1)
        else:
            img_binary = img_binary.erode(1)
            img_binary = img_binary.dilate(2)
        
        # 查找矩形
        all_rects = img_binary.find_rects(threshold=2500)
        
        # 释放处理图像以节省内存
        if not high_perf_mode:
            del img_processed
        del img_binary
        
        # 过滤矩形
        valid_rects = []
        large_rect = None
        
        for rect in all_rects:
            # 计算矩形面积
            area = rect.w() * rect.h()
            
            # 计算矩形的周长与面积比例
            perimeter = 2 * (rect.w() + rect.h())
            perimeter_area_ratio = (perimeter * perimeter) / area if area > 0 else 0
            
            # 过滤不符合条件的矩形
            if area < min_rect_area or area > max_rect_area:
                continue
                
            # 理想矩形的比值约为16，允许一定误差
            if abs(perimeter_area_ratio - 16) > 5:
                continue
                
            # 面积最大的可能是外部大矩形
            if large_rect is None or area > large_rect.w() * large_rect.h():
                large_rect = rect
                
            valid_rects.append(rect)
        
        # 平滑大矩形的位置（减少抖动）
        if large_rect is not None and prev_large_rect is not None:
            # 平滑位置
            smoothed_x = int(prev_large_rect.x() * smooth_factor + large_rect.x() * (1 - smooth_factor))
            smoothed_y = int(prev_large_rect.y() * smooth_factor + large_rect.y() * (1 - smooth_factor))
            smoothed_w = int(prev_large_rect.w() * smooth_factor + large_rect.w() * (1 - smooth_factor))
            smoothed_h = int(prev_large_rect.h() * smooth_factor + large_rect.h() * (1 - smooth_factor))
            
            try:
                # 尝试更新大矩形位置
                large_rect.set_x(smoothed_x)
                large_rect.set_y(smoothed_y)
                large_rect.set_w(smoothed_w)
                large_rect.set_h(smoothed_h)
            except:
                pass
                
        # 更新上一帧的大矩形
        if large_rect is not None:
            prev_large_rect = large_rect
        
        # 标记大矩形（外部矩形）
        if large_rect is not None:
            img.draw_rectangle(large_rect.rect(), color=(255, 0, 0), thickness=2)
            
            # 获取大矩形的边界
            large_x, large_y, large_w, large_h = large_rect.rect()
            
            # 将图像划分为3x3网格
            grid_w = large_w / 3
            grid_h = large_h / 3
            
            # 创建网格结构
            current_grid = {i: None for i in range(1, 10)}
            
            # 识别大矩形内部的小矩形
            for rect in valid_rects:
                if rect == large_rect:
                    continue
                    
                # 计算矩形中心点
                cx = rect.x() + rect.w() // 2
                cy = rect.y() + rect.h() // 2
                
                # 判断是否在大矩形内部
                margin = 5  # 边缘容差
                if (large_x - margin <= cx <= large_x + large_w + margin and
                    large_y - margin <= cy <= large_y + large_h + margin):
                    
                    # 计算相对于大矩形的位置
                    rel_x = cx - large_x
                    rel_y = cy - large_y
                    
                    # 计算网格坐标
                    grid_col = min(max(int(rel_x / grid_w), 0), 2)
                    grid_row = min(max(int(rel_y / grid_h), 0), 2)
                    
                    # 计算网格编号（从1到9）
                    grid_num = grid_row * 3 + grid_col + 1
                    
                    # 将矩形分配到相应的网格
                    current_grid[grid_num] = rect
            
            # 处理每个网格位置的矩形
            for grid_num in range(1, 10):
                rect = current_grid[grid_num]
                
                if rect is not None:
                    # 当前帧检测到矩形，增加稳定帧计数
                    inner_valid_frames[grid_num] = min(inner_valid_frames[grid_num] + 1, 10)
                    
                    # 更新历史矩形
                    prev_inner_grid[grid_num] = rect
                    
                    # 计算矩形中心点
                    cx = rect.x() + rect.w() // 2
                    cy = rect.y() + rect.h() // 2
                    
                    # 绘制小矩形
                    img.draw_rectangle(rect.rect(), color=(0, 255, 0), thickness=2)
                    
                    # 在矩形中心显示网格编号
                    img.draw_string(cx - 4, cy - 8, str(grid_num), color=(255, 0, 255), scale=1)
                else:
                    # 当前帧未检测到矩形，检查历史记录
                    if prev_inner_grid[grid_num] is not None and inner_valid_frames[grid_num] >= valid_frames_threshold:
                        # 使用历史矩形
                        prev_rect = prev_inner_grid[grid_num]
                        
                        # 计算矩形中心点
                        cx = prev_rect.x() + prev_rect.w() // 2
                        cy = prev_rect.y() + prev_rect.h() // 2
                        
                        # 绘制小矩形（使用不同颜色标记历史矩形）
                        img.draw_rectangle(prev_rect.rect(), color=(0, 200, 200), thickness=2)
                        
                        # 在矩形中心显示网格编号
                        img.draw_string(cx - 4, cy - 8, str(grid_num), color=(200, 200, 0), scale=1)
                    else:
                        # 不够稳定或没有历史记录，逐渐减少稳定帧计数
                        inner_valid_frames[grid_num] = max(inner_valid_frames[grid_num] - 1, 0)
        
        # 如果没有检测到大矩形但有历史记录，使用历史数据
        elif prev_large_rect is not None:
            img.draw_rectangle(prev_large_rect.rect(), color=(200, 100, 0), thickness=2)

        # 显示捕获的图像，中心对齐，居中显示
        Display.show_image(img, x=int((DISPLAY_WIDTH - picture_width) / 2), y=int((DISPLAY_HEIGHT - picture_height) / 2))

except KeyboardInterrupt as e:
    print("用户停止: ", e)
except BaseException as e:
    print(f"异常: {e}")
finally:
    # 停止传感器运行
    if isinstance(sensor, Sensor):
        sensor.stop()
    # 反初始化显示模块
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # 释放媒体缓冲区
    MediaManager.deinit()
