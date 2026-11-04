/*
 * Intégration du décodeur TIC sur la NUCLEO-N657X0-Q (STM32CubeIDE, HAL).
 * Ce fichier n'est pas à compiler tel quel : chaque bloc est à coller dans la section
 * « USER CODE » indiquée du main.c généré par STM32CubeIDE.
 *
 * Réglages dans le .ioc (USART relié au ST-LINK, probablement USART1 : PE5 TX / PE6 RX) :
 *   Mode Asynchronous ; Baud Rate 9600 (1200 en mode historique) ;
 *   Word Length 8 Bits (including Parity) ; Parity Even ; Stop Bits 1 ;
 *   NVIC Settings : cocher « USART1 global interrupt ».
 * Copier tic_decodeur.h dans Core/Inc et tic_decodeur.c dans Core/Src.
 */

/* ===== USER CODE BEGIN Includes ===== */
#include "tic_decodeur.h"

/* ===== USER CODE BEGIN PV ===== */
tic_t tic;                       /* à surveiller dans « Live Expressions » pendant le débogage */
static uint8_t octet_rx;
volatile uint32_t nb_octets_recus;   /* sert à vérifier que des octets arrivent */

/* ===== USER CODE BEGIN 2 (après les MX_..._Init) ===== */
tic_init(&tic);
HAL_UART_Receive_IT(&huart1, &octet_rx, 1);

/* ===== USER CODE BEGIN 4 ===== */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        nb_octets_recus++;
        if (tic_octet(&tic, octet_rx) == TIC_TRAME_OK) {
            /* une trame complète et valide : tic.papp_va contient la puissance apparente (VA) */
            /* témoin visuel facultatif : remplacer par le nom de la LED du .ioc, ou supprimer */
            /* HAL_GPIO_TogglePin(LED_GREEN_GPIO_Port, LED_GREEN_Pin); */
        }
        HAL_UART_Receive_IT(&huart1, &octet_rx, 1);
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    /* erreur de parité, de trame ou débordement : on relance simplement la réception
       (une ligne abîmée sera de toute façon rejetée par la somme de contrôle) */
    if (huart->Instance == USART1) {
        HAL_UART_Receive_IT(&huart1, &octet_rx, 1);
    }
}
