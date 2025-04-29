# 立创·庐山派-K230-CanMV开发板资料与相关扩展板软硬件资料官网全部开源
# 开发板官网：www.lckfb.com
# 技术支持常驻论坛，任何技术问题欢迎随时交流学习
# 立创论坛：www.jlc-bbs.com/lckfb
# 关注bilibili账号：【立创开发板】，掌握我们的最新动态！
# 不靠卖板赚钱，以培养中国工程师为己任

import time, os, sys
import math

from media.sensor import *
from media.display import *
from media.media import *

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

    # 设置通道0的输出尺寸为显示分辨率
    sensor.set_framesize(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, chn=CAM_CHN_ID_0)
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

    # 优化的蓝色颜色阈值 (LAB颜色空间)
    # 格式：[min_L, max_L, min_A, max_A, min_B, max_B]
    blue_threshold = [(0, 100, -20, 20, -128, -10)]  # 调整为更适合蓝色的阈值

    # 画面中线坐标
    center_x = DISPLAY_WIDTH // 2
    center_y = DISPLAY_HEIGHT // 2

    while True:
        os.exitpoint()

        # 捕获通道0的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)

        # 绘制画面中线
        img.draw_line(center_x, 0, center_x, DISPLAY_HEIGHT, color=(255, 0, 0), thickness=1)  # 红色垂直中线

        # 使用更低的area_threshold以检测更小的蓝色区域，同时启用像素过滤和合并边界
        blobs = img.find_blobs(blue_threshold, area_threshold=1000, 
                              pixels_threshold=100, merge=True)

        # 初始化变量以找到最大的蓝色区域
        max_blob = None
        max_area = 0

        # 如果检测到颜色块
        if blobs:
            # 找出最大的蓝色区域
            for blob in blobs:
                area = blob[2] * blob[3]  # 面积 = 宽 * 高
                if area > max_area:
                    max_area = area
                    max_blob = blob
            
            if max_blob:
                # 获取蓝色区域的关键信息
                x, y, w, h = max_blob[0:4]
                cx, cy = max_blob[5], max_blob[6]  # 中心坐标
                
                # 计算与画面中线的X轴偏移量（正值表示在右侧，负值表示在左侧）
                x_offset = cx - center_x
                
                # 计算角度偏移量（近似值）
                # 使用反正切函数计算角度，将弧度转换为度数
                angle_offset = math.degrees(math.atan2(x_offset, center_y))
                
                # 绘制颜色块的外接矩形
                img.draw_rectangle(x, y, w, h, color=(0, 255, 0), thickness=2)
                
                # 在颜色块的中心绘制一个十字
                img.draw_cross(cx, cy, color=(255, 0, 0), size=10, thickness=2)
                
                # 绘制从画面中心到蓝色区域中心的连线
                img.draw_line(center_x, center_y, cx, cy, color=(255, 255, 0), thickness=2)
                
                # 在图像上显示计算出的信息
                img.draw_string(10, 10, f"X偏移: {x_offset}px", color=(255, 255, 255), scale=1)
                img.draw_string(10, 30, f"角度偏移: {angle_offset:.1f}度", color=(255, 255, 255), scale=1)
                
                # 在控制台输出详细信息
                print(f"蓝色区域中心: X={cx}, Y={cy}, X偏移={x_offset}px, 角度偏移={angle_offset:.1f}度")

        # 显示捕获的图像
        Display.show_image(img)

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
