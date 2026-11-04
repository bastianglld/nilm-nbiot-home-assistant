/*
 * Intégration du décodeur TIC sur la NUCLEO-N657X0-Q (STM32CubeMX + STM32CubeIDE, HAL).
 * Ce fichier n'est pas à compiler tel quel : chaque bloc est à coller dans la section
 * « USER CODE » indiquée du main.c généré (projet FSBL).
 *
 * Sur cette carte, le port série du ST-LINK (USART1, PE5/PE6) est géré par le BSP sous le nom COM1 :
 * dans CubeMX, catégorie Bsp > NUCLEO-N657X0-Q, contexte FSBL, case « Virtual Com Port » cochée.
 * CubeMX l'initialise en 115200 bauds 8N1 ; on le réinitialise ici au format TIC :
 * 9 600 bauds (1 200 en mode historique), 7 bits de données + parité paire = mot de 8 bits, 1 stop.
 *
 * Pour ce premier test, la réception se fait par scrutation dans la boucle principale :
 * pas d'interruption à configurer. À 9 600 bauds (960 octets/s), la boucle suit sans problème.
 *
 * Copier tic_decodeur.h dans FSBL/Core/Inc et tic_decodeur.c dans FSBL/Core/Src.
 */

/* ===== USER CODE BEGIN Includes ===== */
#include "tic_decodeur.h"

/* ===== USER CODE BEGIN PV ===== */
tic_t tic;                               /* à surveiller dans « Live Expressions » */
volatile uint32_t nb_octets_recus;       /* vérifie que des octets arrivent */
volatile uint32_t nb_erreurs_uart;       /* erreurs de parité, de trame ou débordements */

/* ===== USER CODE BEGIN WHILE (avant « while (1) ») ===== */
/* Ce bloc doit venir APRÈS BSP_COM_Init(COM1, ...) : USER CODE BEGIN 2 est trop tôt
   dans le main.c généré pour cette carte, USER CODE BEGIN WHILE convient. */
BSP_COM_DeInit(COM1);
BspCOMInit.BaudRate   = 9600;
BspCOMInit.WordLength = COM_WORDLENGTH_8B;     /* 7 bits de données + 1 bit de parité */
BspCOMInit.StopBits   = COM_STOPBITS_1;
BspCOMInit.Parity     = COM_PARITY_EVEN;
BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE) {
    Error_Handler();
}
tic_init(&tic);

/* ===== USER CODE BEGIN 3 (dans la boucle while (1)) ===== */
uint8_t octet;
HAL_StatusTypeDef st = HAL_UART_Receive(&hcom_uart[COM1], &octet, 1, 5);
if (st == HAL_OK) {
    nb_octets_recus++;
    if (tic_octet(&tic, octet) == TIC_TRAME_OK) {
        BSP_LED_Toggle(LED_GREEN);            /* la LED verte change d'état à chaque trame valide */
    }
} else if (st == HAL_ERROR) {
    nb_erreurs_uart++;                         /* la ligne concernée sera rejetée par la somme de contrôle */
    __HAL_UART_CLEAR_FLAG(&hcom_uart[COM1], UART_CLEAR_PEF | UART_CLEAR_FEF | UART_CLEAR_NEF | UART_CLEAR_OREF);
    hcom_uart[COM1].ErrorCode = HAL_UART_ERROR_NONE;
    hcom_uart[COM1].RxState = HAL_UART_STATE_READY;
}
/* HAL_TIMEOUT : aucun octet pendant 5 ms, on recommence simplement */
