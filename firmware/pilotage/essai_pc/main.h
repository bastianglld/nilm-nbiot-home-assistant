/* En-tête minimal remplaçant main.h (HAL et BSP) pour essai_appli_pc.c */
#include <stdint.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { uint32_t ErrorCode; uint32_t RxState; } UART_HandleTypeDef;
extern UART_HandleTypeDef hcom_uart[];
#define COM1 0
#define LED_RED 0
#define LED_GREEN 1
#define LED_BLUE 2
#define UART_CLEAR_PEF 1
#define UART_CLEAR_FEF 2
#define UART_CLEAR_NEF 4
#define UART_CLEAR_OREF 8
#define HAL_UART_ERROR_NONE 0
#define HAL_UART_STATE_READY 0
#define __HAL_UART_CLEAR_FLAG(h,f) ((void)(h),(void)(f))
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef*, const uint8_t*, uint16_t, uint32_t);
HAL_StatusTypeDef HAL_UART_Receive(UART_HandleTypeDef*, uint8_t*, uint16_t, uint32_t);
void BSP_LED_On(int); void BSP_LED_Off(int); void BSP_LED_Toggle(int);
uint32_t HAL_GetTick(void);
