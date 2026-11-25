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

/* Sorties relais (étiquettes CubeMX RELAIS_BAT et RELAIS_CE) : sur PC, chaque écriture affiche une ligne « GPIO … » */
typedef struct { const char *nom; } GPIO_TypeDef;
typedef enum { GPIO_PIN_RESET = 0, GPIO_PIN_SET = 1 } GPIO_PinState;
extern GPIO_TypeDef essai_port_bat, essai_port_ce;
#define RELAIS_BAT_GPIO_Port (&essai_port_bat)
#define RELAIS_BAT_Pin       ((uint16_t)0x0800)   /* PE11 */
#define RELAIS_CE_GPIO_Port  (&essai_port_ce)
#define RELAIS_CE_Pin        ((uint16_t)0x1000)   /* PD12 */
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState etat);

/* Jauge de la batterie virtuelle (étiquettes CubeMX JAUGE1 à JAUGE5) */
extern GPIO_TypeDef essai_port_j1, essai_port_j2, essai_port_j3, essai_port_j4, essai_port_j5;
#define JAUGE1_GPIO_Port (&essai_port_j1)
#define JAUGE1_Pin       ((uint16_t)0x0001)   /* PD0 */
#define JAUGE2_GPIO_Port (&essai_port_j2)
#define JAUGE2_Pin       ((uint16_t)0x0200)   /* PE9 */
#define JAUGE3_GPIO_Port (&essai_port_j3)
#define JAUGE3_Pin       ((uint16_t)0x0001)   /* PE0 */
#define JAUGE4_GPIO_Port (&essai_port_j4)
#define JAUGE4_Pin       ((uint16_t)0x0400)   /* PE10 */
#define JAUGE5_GPIO_Port (&essai_port_j5)
#define JAUGE5_Pin       ((uint16_t)0x0020)   /* PD5 */
