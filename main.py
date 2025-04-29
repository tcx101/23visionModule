# 立创·庐山派-K230-CanMV开发板资料与相关扩展板软硬件资料官网全部开源
# 开发板官网：www.lckfb.com
# 技术支持常驻论坛，任何技术问题欢迎随时交流学习
# 立创论坛：www.jlc-bbs.com/lckfb
# 关注bilibili账号：【立创开发板】，掌握我们的最新动态！
# 不靠卖板赚钱，以培养中国工程师为己任

import time, os, sys
import gc
import struct

from media.sensor import *
from media.display import *
from media.media import *
from machine import UART
from machine import FPIOA

# 设置图像分辨率
picture_width = 480
picture_height = 320

# 性能模式（True: 高性能，False: 高精度）
high_perf_mode = True

sensor_id = 2
sensor = None

# 显示模式选择：可以是 "VIRT"、"LCD" 或 "HDMI"
DISPLAY_MODE = "LCD"

# 配置串口
fpioa = FPIOA()
fpioa.set_function(11, FPIOA.UART2_TXD)
fpioa.set_function(12, FPIOA.UART2_RXD)

# 初始化UART2，波特率115200，8位数据位，无校验，1位停止位
uart = UART(UART.UART2, baudrate=115200, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)

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

    # 更改绿色LAB阈值，使其更严格
    green_threshold = (80, 100, -54, -25, -128, 127)  # 修改后的LAB色彩空间阈值

    # 定义绿色色块检测参数
    min_green_area = 3  # 增加最小面积要求，避免噪点
    max_green_area = 2000  # 最大绿色色块面积
    min_green_pixels = 1  # 增加最小像素数量

    # 自适应矩形面积阈值（基于图像尺寸）
    min_rect_area = int(picture_width * picture_height * 0.002)
    max_rect_area = picture_width * picture_height * 0.5

    # 帧率计时器
    last_time = time.ticks_ms()
    frame_count = 0

    # 调试模式开关，设为False可以关闭大部分打印信息
    debug_mode = False

    # 添加时间平滑处理的变量，只为矩形平滑，不为绿色色块平滑
    prev_outer_rect = None
    prev_inner_rect = None
    smoothing_factor = 0.7  # 平滑系数，值越大表示历史数据权重越大

    # 帧稳定性计数器
    stable_frames = 0
    min_stable_frames = 3  # 最少需要连续稳定的帧数

    # 存储上一帧的有效检测结果
    last_valid_outer_rect = None
    last_valid_inner_rect = None

    # 检测结果有效性标志
    had_valid_detection = False

    # 缓存上一次检测的二值化图像阈值结果
    last_binary_threshold = 45

    # 垃圾回收计数器
    gc_counter = 0

    while True:
        os.exitpoint()

        # 捕获通道0的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)

        # 高性能模式下，不创建不必要的副本
        if high_perf_mode:
            # 只为绿色检测创建副本
            img_green = img.copy()
            img_rect = img  # 直接使用原始图像
        else:
            # 保存原始图像用于绿色检测和矩形检测
            img_green = img.copy()
            img_rect = img.copy()

        # 对绿色检测图像进行降噪和预处理
        if not high_perf_mode:
            img_green.bilateral(1, color_sigma=0.1, space_sigma=1)
        
        # 创建二值化图像用于检测黑色边框
        if high_perf_mode:
            img_binary = img_rect.binary([(0, last_binary_threshold)], invert=False)
            # 简化形态学处理
            img_binary = img_binary.dilate(1)
        else:
            # 使用更强的滤波和形态学操作
            img_binary = img_rect.copy().bilateral(2, color_sigma=0.2, space_sigma=2)
            img_binary = img_binary.binary([(0, 45)], invert=False)
            img_binary = img_binary.erode(1)
            img_binary = img_binary.dilate(1)

        # 使用二值化图像查找矩形
        rects = img_binary.find_rects(threshold=2000)

        # 释放二值化图像，避免内存问题
        del img_binary

        # 根据矩形面积和比例进行过滤，只保留可能是边框的矩形
        valid_rects = []
        for rect in rects:
            # 计算矩形宽高比
            ratio = max(rect.w(), rect.h()) / min(rect.w(), rect.h())
            # 矩形面积
            area = rect.w() * rect.h()

            # 使用更严格的比例限制，确保矩形更接近正方形
            if ratio < 1.25 and area > min_rect_area and area < max_rect_area:
                # 检查矩形的周长与面积比例是否合理（矩形周长的平方/面积应该接近16）
                perimeter = rect.w() * 2 + rect.h() * 2
                perimeter_area_ratio = (perimeter * perimeter) / area

                # 理想矩形的比值约为16，允许有10%的误差
                if 14.4 < perimeter_area_ratio < 17.6:
                    valid_rects.append(rect)

        # 改进的矩形排序和筛选逻辑
        sorted_rects = []
        if len(valid_rects) >= 2:
            # 首先按面积排序
            area_sorted_rects = sorted(valid_rects, key=lambda r: r.w() * r.h(), reverse=True)

            # 检查是否存在嵌套关系（内圈必须在外圈内部）
            outer_rect = area_sorted_rects[0]  # 假设最大的是外圈
            outer_center_x = outer_rect.x() + outer_rect.w() // 2
            outer_center_y = outer_rect.y() + outer_rect.h() // 2

            # 添加外圈
            sorted_rects.append(outer_rect)

            # 寻找内圈 - 必须在外圈内部且是所有候选中最大的
            inner_candidates = []
            for rect in area_sorted_rects[1:]:
                # 检查矩形中心是否在外圈内部
                rect_center_x = rect.x() + rect.w() // 2
                rect_center_y = rect.y() + rect.h() // 2

                # 检查该矩形中心是否在外圈内部
                if (outer_rect.x() <= rect_center_x <= outer_rect.x() + outer_rect.w() and
                    outer_rect.y() <= rect_center_y <= outer_rect.y() + outer_rect.h()):
                    inner_candidates.append(rect)

            # 如果找到内圈候选，选择最大的一个作为内圈
            if inner_candidates:
                inner_candidates.sort(key=lambda r: r.w() * r.h(), reverse=True)
                sorted_rects.append(inner_candidates[0])
            elif len(area_sorted_rects) > 1:
                # 如果没有找到嵌套关系，但有多个矩形，就选面积第二大的
                sorted_rects.append(area_sorted_rects[1])
        else:
            # 如果没有足够的矩形，直接使用面积排序
            sorted_rects = sorted(valid_rects, key=lambda r: r.w() * r.h(), reverse=True)

        # 应用时间平滑来减少闪烁
        current_detection_valid = False

        if len(sorted_rects) >= 2:
            # 获取当前帧的外圈和内圈
            current_outer_rect = sorted_rects[0]
            current_inner_rect = sorted_rects[1]

            # 判断当前检测是否有效
            # 计算内外圈尺寸比例
            inner_size = (current_inner_rect.w() + current_inner_rect.h()) / 2
            outer_size = (current_outer_rect.w() + current_outer_rect.h()) / 2
            size_ratio = inner_size / outer_size if outer_size > 0 else 0

            # 计算内外圈中心点的距离
            inner_center_x = current_inner_rect.x() + current_inner_rect.w() // 2
            inner_center_y = current_inner_rect.y() + current_inner_rect.h() // 2
            outer_center_x = current_outer_rect.x() + current_outer_rect.w() // 2
            outer_center_y = current_outer_rect.y() + current_outer_rect.h() // 2
            center_distance = ((inner_center_x - outer_center_x)**2 +
                              (inner_center_y - outer_center_y)**2)**0.5

            # 检测是否在合理范围内
            if (0.4 <= size_ratio <= 0.95 and
                center_distance <= (current_outer_rect.w() + current_outer_rect.h()) / 4):
                current_detection_valid = True

                # 更新最近有效的检测结果
                last_valid_outer_rect = current_outer_rect
                last_valid_inner_rect = current_inner_rect

                # 增加稳定帧计数
                stable_frames += 1

                # 应用平滑处理
                if prev_outer_rect is not None and prev_inner_rect is not None:
                    # 平滑外圈位置
                    smooth_outer_x = int(prev_outer_rect.x() * smoothing_factor +
                                       current_outer_rect.x() * (1 - smoothing_factor))
                    smooth_outer_y = int(prev_outer_rect.y() * smoothing_factor +
                                       current_outer_rect.y() * (1 - smoothing_factor))
                    smooth_outer_w = int(prev_outer_rect.w() * smoothing_factor +
                                       current_outer_rect.w() * (1 - smoothing_factor))
                    smooth_outer_h = int(prev_outer_rect.h() * smoothing_factor +
                                       current_outer_rect.h() * (1 - smoothing_factor))

                    # 平滑内圈位置
                    smooth_inner_x = int(prev_inner_rect.x() * smoothing_factor +
                                       current_inner_rect.x() * (1 - smoothing_factor))
                    smooth_inner_y = int(prev_inner_rect.y() * smoothing_factor +
                                       current_inner_rect.y() * (1 - smoothing_factor))
                    smooth_inner_w = int(prev_inner_rect.w() * smoothing_factor +
                                       current_inner_rect.w() * (1 - smoothing_factor))
                    smooth_inner_h = int(prev_inner_rect.h() * smoothing_factor +
                                       current_inner_rect.h() * (1 - smoothing_factor))

                    try:
                        # 更新外圈
                        current_outer_rect.set_x(smooth_outer_x)
                        current_outer_rect.set_y(smooth_outer_y)
                        current_outer_rect.set_w(smooth_outer_w)
                        current_outer_rect.set_h(smooth_outer_h)

                        # 更新内圈
                        current_inner_rect.set_x(smooth_inner_x)
                        current_inner_rect.set_y(smooth_inner_y)
                        current_inner_rect.set_w(smooth_inner_w)
                        current_inner_rect.set_h(smooth_inner_h)
                    except Exception as e:
                        if debug_mode:
                            print(f"矩形平滑处理发生错误: {e}")

                    # 更新排序后的矩形列表
                    sorted_rects[0] = current_outer_rect
                    sorted_rects[1] = current_inner_rect

                # 更新上一帧的矩形
                prev_outer_rect = current_outer_rect
                prev_inner_rect = current_inner_rect
                had_valid_detection = True
            else:
                # 当前帧检测无效，重置稳定帧计数
                stable_frames = 0

                # 如果有之前有效的检测结果，使用它
                if had_valid_detection and last_valid_outer_rect is not None and last_valid_inner_rect is not None:
                    sorted_rects[0] = last_valid_outer_rect
                    if len(sorted_rects) > 1:
                        sorted_rects[1] = last_valid_inner_rect
                    else:
                        sorted_rects.append(last_valid_inner_rect)
        else:
            # 没有足够的矩形，重置稳定帧计数
            stable_frames = 0

            # 如果有之前有效的检测结果，使用它
            if had_valid_detection and last_valid_outer_rect is not None and last_valid_inner_rect is not None:
                sorted_rects = [last_valid_outer_rect, last_valid_inner_rect]

        # 改进的绿色色块检测 - 高性能模式下简化处理
        final_green_blobs = []
        try:
            # 使用修改后的阈值元组进行高效检测
            all_green_blobs = img_green.find_blobs([green_threshold],
                                        area_threshold=min_green_area,
                                        pixels_threshold=min_green_pixels,
                                        merge=True)

            # 高效过滤绿色色块
            if all_green_blobs:
                if high_perf_mode and len(all_green_blobs) > 0:
                    # 高性能模式下只取面积最大的绿色块
                    all_green_blobs.sort(key=lambda b: b.area(), reverse=True)
                    final_green_blobs = [all_green_blobs[0]]
                else:
                    # 标准模式下进行完整过滤
                    for blob in all_green_blobs:
                        # 计算圆度
                        perimeter = blob.perimeter()
                        if perimeter == 0:  # 避免除以零错误
                            continue

                        area = blob.area()
                        circularity = 4 * 3.14159 * area / (perimeter * perimeter)

                        # 圆度大于0.6且面积在指定范围内
                        if (min_green_area <= area <= max_green_area and
                            circularity > 0.6):  # 圆度要求
                            final_green_blobs.append(blob)

                    # 按圆度排序，更圆的在前面
                    if len(final_green_blobs) > 1:
                        final_green_blobs.sort(key=lambda b: 4 * 3.14159 * b.area() / 
                                             (b.perimeter() * b.perimeter() if b.perimeter() > 0 else 1), 
                                             reverse=True)
                        final_green_blobs = final_green_blobs[:1]  # 只保留最佳的一个

        except Exception as e:
            if debug_mode:
                print(f"绿色检测错误: {e}")
            final_green_blobs = []
        
        # 释放绿色检测图像
        del img_green

        # 检查是否有外圈和内圈
        if len(sorted_rects) >= 2:
            # 获取外圈和内圈
            outer_rect = sorted_rects[0]
            inner_rect = sorted_rects[1]

            # 直接获取原始检测到的矩形顶点
            outer_corners = outer_rect.corners()
            inner_corners = inner_rect.corners()

            # 计算内部矩形的中心点
            inner_center_x = inner_rect.x() + inner_rect.w() // 2
            inner_center_y = inner_rect.y() + inner_rect.h() // 2

            # 额外验证：确保内圈在外圈内部
            outer_center_x = outer_rect.x() + outer_rect.w() // 2
            outer_center_y = outer_rect.y() + outer_rect.h() // 2

            # 计算内外圈中心点的距离
            center_distance = ((inner_center_x - outer_center_x)**2 +
                              (inner_center_y - outer_center_y)**2)**0.5

            # 计算内外圈尺寸比例
            inner_size = (inner_rect.w() + inner_rect.h()) / 2
            outer_size = (outer_rect.w() + outer_rect.h()) / 2
            size_ratio = inner_size / outer_size if outer_size > 0 else 0

            # 如果内圈中心距离外圈中心太远或尺寸比例不合理，可能是错误识别
            is_valid_nesting = True
            if center_distance > (outer_rect.w() + outer_rect.h()) / 4:
                is_valid_nesting = False
            elif size_ratio < 0.4 or size_ratio > 0.95:
                is_valid_nesting = False

            # 如果内外圈定位有问题，尝试修正（仅在非高性能模式下）
            if not is_valid_nesting and not high_perf_mode and len(valid_rects) > 2:
                # 对所有候选重新评估
                better_inner = None
                best_score = float('inf')

                for rect in valid_rects:
                    # 跳过当前的外圈
                    if rect == outer_rect:
                        continue

                    # 计算中心点距离和尺寸比例
                    rect_cx = rect.x() + rect.w() // 2
                    rect_cy = rect.y() + rect.h() // 2
                    dist = ((rect_cx - outer_center_x)**2 + (rect_cy - outer_center_y)**2)**0.5
                    rect_size = (rect.w() + rect.h()) / 2
                    ratio = rect_size / outer_size

                    # 综合评分: 距离越小越好，尺寸比例越合理越好
                    # 理想的内圈尺寸比例约为0.6-0.7
                    dist_score = dist / outer_size
                    ratio_score = abs(0.65 - ratio) * 2
                    total_score = dist_score + ratio_score

                    # 如果找到更好的内圈
                    if total_score < best_score and ratio > 0.4 and ratio < 0.9:
                        best_score = total_score
                        better_inner = rect

                # 如果找到更好的内圈，更新内圈
                if better_inner is not None:
                    inner_rect = better_inner
                    inner_corners = inner_rect.corners()
                    inner_center_x = inner_rect.x() + inner_rect.w() // 2
                    inner_center_y = inner_rect.y() + inner_rect.h() // 2
                    sorted_rects[1] = better_inner

            # 直接使用原始图像（高性能模式）或创建副本（标准模式）
            if high_perf_mode:
                img_copy = img
            else:
                img_copy = img.copy()

            # 在图像上标记内部矩形的中心点
            img_copy.draw_cross(inner_center_x, inner_center_y, color=(255, 0, 0), size=10, thickness=2)
            img_copy.draw_circle(inner_center_x, inner_center_y, 5, color=(255, 0, 0), thickness=2)

            # 在图像上标记外部矩形的中心点
            img_copy.draw_cross(outer_center_x, outer_center_y, color=(255, 255, 0), size=10, thickness=2)
            img_copy.draw_circle(outer_center_x, outer_center_y, 5, color=(255, 255, 0), thickness=2)

            # 构建数据字符串
            data_str = "@"

            # 发送外圈四个顶点的原始坐标
            for corner in outer_corners:
                data_str += f"{corner[0]},{corner[1]},"

            # 发送内圈四个顶点的原始坐标
            for i, corner in enumerate(inner_corners):
                if i < 3:
                    data_str += f"{corner[0]},{corner[1]},"
                else:
                    data_str += f"{corner[0]},{corner[1]}"

            # 添加内部矩形中心点坐标
            data_str += f",{inner_center_x},{inner_center_y}"

            # 如果有检测到绿色色块，添加绿色色块坐标
            if final_green_blobs:
                green_blob = final_green_blobs[0]  # 取最佳的绿色色块
                data_str += f",{green_blob.cx()},{green_blob.cy()}"

            # 添加结束符
            data_str += "#\r\n"

            # 通过串口发送数据
            if debug_mode:
                print("发送数据:", data_str)
                print(f"内部矩形中心点: ({inner_center_x}, {inner_center_y})")
                if len(final_green_blobs) > 0:
                    print(f"绿色色块中心点: ({final_green_blobs[0].cx()}, {final_green_blobs[0].cy()})")
            uart.write(data_str)

            # 绘制矩形
            for i, rect in enumerate(sorted_rects):
                # 获取矩形的四个顶点（按顺时针顺序）
                corners = rect.corners()

                # 根据矩形的大小（排序后的索引）区分内外圈
                if i == 0:  # 最外圈
                    line_color = (0, 180, 0)  # 绿色
                    line_thickness = 2
                elif i == 1:  # 第二圈
                    line_color = (230, 50, 50)  # 红色
                    line_thickness = 2
                else:  # 其他内圈
                    line_color = (1, 147, 230)  # 蓝色
                    line_thickness = 2

                # 连接顶点绘制线段
                for j in range(4):
                    start_point = corners[j]
                    end_point = corners[(j + 1) % 4]
                    img_copy.draw_line(start_point[0], start_point[1], end_point[0], end_point[1], 
                                      color=line_color, thickness=line_thickness)

            # 使用更高效的方式标记绿色色块位置
            if final_green_blobs and len(final_green_blobs) > 0:
                for blob in final_green_blobs:
                    cx = blob.cx()
                    cy = blob.cy()
                    img_copy.draw_circle(cx, cy, 5, color=(0, 255, 0), thickness=2)
                    img_copy.draw_cross(cx, cy, color=(0, 255, 0), size=10, thickness=2)
        
        else:
            # 没有检测到矩形，使用原始图像
            img_copy = img

        # 显示捕获的图像，中心对齐，居中显示
        Display.show_image(img_copy, x=int((DISPLAY_WIDTH - picture_width) / 2), y=int((DISPLAY_HEIGHT - picture_height) / 2))

        # 计算并显示帧率(每秒更新一次)
        frame_count += 1
        if time.ticks_ms() - last_time >= 1000:
            fps = frame_count
            if debug_mode:
                print(f"FPS: {fps}")
            frame_count = 0
            last_time = time.ticks_ms()

        # 定期触发垃圾回收，而不是每帧都触发
        gc_counter += 1
        if gc_counter >= 10:  # 每10帧执行一次
            gc.collect()
            gc_counter = 0

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
    # 释放UART资源
    uart.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # 释放媒体缓冲区
    MediaManager.deinit()
