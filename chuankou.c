#include "chuankou.h"
#include <string.h>
#include <stdlib.h>

char str[200];
zuobiao dingdian;

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart == &huart1 && Size > 0)
    {
        // 检查是否收到完整数据（以@开头，以#结尾）
        if (str[0] == '@')
        {
            char *p = str + 1; // 跳过@符号
            char *end;
            
            // 解析8个点的坐标（16个值）
            // 外圈四个点
            dingdian.x1 = strtol(p, &end, 10);
            p = end + 1; // 跳过逗号
            dingdian.y1 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x2 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y2 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x3 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y3 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x4 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y4 = strtol(p, &end, 10);
            p = end + 1;
            
            // 内圈四个点
            dingdian.x5 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y5 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x6 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y6 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x7 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y7 = strtol(p, &end, 10);
            p = end + 1;
            
            dingdian.x8 = strtol(p, &end, 10);
            p = end + 1;
            dingdian.y8 = strtol(p, &end, 10);
        }
        
        // 重新启动DMA接收
        HAL_UARTEx_ReceiveToIdle_DMA(&huart1, (uint8_t *)str, sizeof(str));
    }
}
