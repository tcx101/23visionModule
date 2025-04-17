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

picture_width = 400
picture_height = 240

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

    # 设置通道0的输出尺寸为1920x1080
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

    # 定义绿色阈值 (LAB格式)
    green_threshold = (72, 100, -128, 127, -128, 127)  # 绿色阈值范围

    # 定义绿色色块检测参数
    min_green_area = 1  # 最小绿色色块面积
    max_green_area = 800  # 最大绿色色块面积
    min_green_pixels = 2  # 增加最小像素数量，减少噪点干扰

    while True:
        os.exitpoint()

        # 捕获通道0的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)

        # 保存原始图像用于绿色检测
        img_copy = img.copy()

        # 对绿色检测图像进行降噪处理
        img_copy.bilateral(1, color_sigma=0.1, space_sigma=1)

        # 创建二值化图像用于检测黑色边框
        img_binary = img.copy().binary([(0, 50)], invert=False)  # 较低阈值以突出黑色部分

        # 使用二值化图像查找矩形
        rects = img_binary.find_rects(threshold=2000)
        count = 0  # 初始化线段计数器

        # 释放二值化图像，避免内存问题
        del img_binary

        # 根据矩形面积和比例进行过滤，只保留可能是边框的矩形
        valid_rects = []
        for rect in rects:
            # 计算矩形宽高比
            ratio = max(rect.w(), rect.h()) / min(rect.w(), rect.h())
            # 矩形面积
            area = rect.w() * rect.h()

            # 只保留宽高比接近1（接近正方形）且面积在合理范围内的矩形
            if ratio < 1.3 and area > 2000 and area < (picture_width * picture_height) / 3:
                valid_rects.append(rect)

        # 根据矩形面积排序，面积大的在前面（外圈），面积小的在后面（内圈）
        sorted_rects = sorted(valid_rects, key=lambda r: r.w() * r.h(), reverse=True)

        # 检测绿色色块
        green_blobs = img_copy.find_blobs([green_threshold],
                                    area_threshold=min_green_area,
                                    pixels_threshold=min_green_pixels,
                                    merge=True)  # 开启合并以减少重复检测

        # 过滤绿色色块
        valid_green_blobs = []
        for blob in green_blobs:
            if min_green_area <= blob.area() <= max_green_area:
                # 额外检查色块的圆形程度，增强防错处理
                perimeter = blob.perimeter()
                if perimeter > 0:  # 确保周长大于0
                    circularity = 4 * 3.14159 * blob.area() / (perimeter * perimeter)
                    if circularity > 0.6:  # 圆形程度阈值
                        valid_green_blobs.append(blob)
                else:
                    # 如果周长为0，直接根据面积判断
                    if blob.area() >= min_green_area:
                        valid_green_blobs.append(blob)

        # 按面积排序绿色色块（面积大的在前）
        valid_green_blobs.sort(key=lambda b: b.area(), reverse=True)

        # 检查是否有外圈和内圈
        if len(sorted_rects) >= 2:
            # 直接获取原始检测到的矩形顶点
            outer_corners = sorted_rects[0].corners()
            inner_corners = sorted_rects[1].corners()

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

            # 如果有检测到绿色色块，添加绿色色块坐标
            if len(valid_green_blobs) > 0:
                green_blob = valid_green_blobs[0]  # 取最大的绿色色块
                data_str += f",{green_blob.cx()},{green_blob.cy()}"

            # 添加结束符
            data_str += "#\r\n"

            # 通过串口发送数据
            print("发送数据:", data_str)
            uart.write(data_str)

        print("------矩形统计开始------")
        print(f"检测到 {len(valid_rects)} 个有效矩形，共 {len(rects)} 个矩形")
        print(f"检测到 {len(valid_green_blobs)} 个有效绿色色块，共 {len(green_blobs)} 个绿色色块")

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
                img_copy.draw_line(start_point[0], start_point[1], end_point[0], end_point[1], color=line_color, thickness=line_thickness)

            # 在每个矩形的左上角标记序号，帮助识别内外圈
            img_copy.draw_string(corners[0][0], corners[0][1], f"{i}", color=(255, 255, 255), scale=1)

            print(f"Rect {count}: {rect}, Area: {rect.w() * rect.h()}, Ratio: {max(rect.w(), rect.h()) / min(rect.w(), rect.h())}")
            count += 1  # 更新计数器

        # 绘制绿色色块
        for blob in valid_green_blobs:
            # 在图像上绘制矩形和绿色色块中心点
            img_copy.draw_rectangle(blob.rect(), color=(0, 255, 0), thickness=1)
            img_copy.draw_cross(blob.cx(), blob.cy(), color=(0, 255, 0), size=5, thickness=1)

        print("---------END---------")

        # 显示捕获的图像，中心对齐，居中显示
        Display.show_image(img_copy, x=int((DISPLAY_WIDTH - picture_width) / 2), y=int((DISPLAY_HEIGHT - picture_height) / 2))

        # 释放原始图像
        del img_copy

        # 手动触发垃圾回收
        gc.collect()

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
