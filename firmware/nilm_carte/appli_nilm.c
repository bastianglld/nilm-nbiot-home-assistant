/* Application de la carte (partie C) – voir appli_nilm.h */
#include <stdio.h>
#include <string.h>
#include "main.h"
#include "appli_nilm.h"
#include "tic_decodeur.h"
#include "mesure_vi.h"
#include "nilm_flux.h"
#include "nilm_ia.h"
#include "pilotage.h"

/* ------------------------------------------------------------------ étalonnage de la mesure */
#define ADC_VOLTS_PAR_POINT  (1.8f / 4096.0f)  /* référence de l'ADC du STM32N6 : 1,8 V */
#define RAPPORT_CARTE        0.54f             /* ampli de la carte entre A0/A1 et PA8/PA9 (mesuré au GBF) */
#define V_CONNECTEUR         (ADC_VOLTS_PAR_POINT / RAPPORT_CARTE)   /* volts sur le connecteur par point ADC */
#define CORRECTION_V         1.0f              /* validé à l'oscilloscope le 6 novembre : pas de correction */
#define CORRECTION_I         1.0f

#if CAPTEURS_REELS
/* tension : adaptateur 230 V -> 9 V (rapport à mesurer au multimètre), pont R5 = 100 kΩ / R6 = 8,2 kΩ */
#define K_V  (V_CONNECTEUR * CORRECTION_V * (100.0f + 8.2f) / 8.2f * (230.0f / 9.0f))
/* courant : pince SCT-013-000 (rapport 2000) sur R3 = 22 Ω, SPIRES tours de fil dans la pince */
#define SPIRES 1.0f
#define K_I  (V_CONNECTEUR * CORRECTION_I / 22.0f * 2000.0f / SPIRES)
#else
#define K_V  (V_CONNECTEUR * CORRECTION_V)
#define K_I  (V_CONNECTEUR * CORRECTION_I)
#endif

/* ------------------------------------------------------------------ état (lisible dans Live Expressions) */
tic_t tic;
mesure_vi_t mes;
nilm_flux_t nilm;
volatile int32_t nilm_etat_ia;           /* 0 = modèle prêt */
volatile uint32_t nb_octets_recus, nb_erreurs_uart;
volatile uint32_t nilm_messages, nilm_erreurs, nilm_duree_us, nilm_envois_rates;
volatile float cadence_hz;               /* échantillons par seconde : ~4000 */
volatile int32_t minute_vi;              /* minute courante en mode V/I */
static volatile uint8_t minute_vi_prete;
static uint32_t t_bloc;
pilotage_t pil;                          /* planning, ordres, état des relais (pilotage.h) */
volatile int32_t minute_actuelle = -1;   /* heure de la carte : TIC, ou mesure V/I, plus tard réseau NB-IoT */
static int32_t minute_pilotee = -1;
static char ligne_rx[96];                /* essais sur PC : lignes « MQTT <topic> <message> » reçues */
static uint8_t ligne_rx_n;

/* ------------------------------------------------------------------ envoi */
/* Un seul point de sortie : aujourd'hui le port du ST-LINK (PC), demain la liaison vers le ST87M01. */
static void envoyer_message(const char *ligne)
{
  if (HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t *)ligne, (uint16_t)strlen(ligne), 100) != HAL_OK)
    nilm_envois_rates++;
}

/* Publication d'un message MQTT. Aujourd'hui : une ligne « MQTT <topic> <message> » vers le PC ;
   demain : AT#MQTTPUB du ST87M01 (partie B). */
static void publier(const char *topic, const char *message)
{
  char ligne[96];
  snprintf(ligne, sizeof ligne, "MQTT %s %s\r\n", topic, message);
  envoyer_message(ligne);
}

/* ------------------------------------------------------------------ sorties relais
 * Deux voies de relais, câblées comme dans le document remis au technicien :
 *   D7 = PE11, étiquette CubeMX RELAIS_BAT -> relais 1 : coupe ou rétablit le +5 V USB de la batterie externe ;
 *   D8 = PD12, étiquette CubeMX RELAIS_CE  -> relais 2 : chauffe-eau (la LED rouge le montre aussi).
 * RELAIS_ACTIF_BAS dit à quel niveau le module colle :
 *   0 : Grove 2-Channel SPDT Relay (Seeed), commande par transistor : 3,3 V = relais collé (module utilisé) ;
 *   1 : module optocouplé à cavalier JD-VCC : 0 V = relais collé.
 * Dans CubeMX : GPIO_Output, contexte FSBL, niveau de départ = repos (Low si RELAIS_ACTIF_BAS vaut 0, High sinon).
 * Tant que ces étiquettes n'existent pas dans main.h, le code compile sans elles : seules la LED et les
 * lignes vers le PC montrent l'état. */
#ifndef RELAIS_ACTIF_BAS
#define RELAIS_ACTIF_BAS 0
#endif

static void sortie_relais(int voie, uint8_t colle)
{
#if defined(RELAIS_BAT_Pin) && defined(RELAIS_CE_Pin)
  GPIO_PinState niveau = (colle != 0) != (RELAIS_ACTIF_BAS != 0) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  if (voie == 1) HAL_GPIO_WritePin(RELAIS_BAT_GPIO_Port, RELAIS_BAT_Pin, niveau);
  else           HAL_GPIO_WritePin(RELAIS_CE_GPIO_Port, RELAIS_CE_Pin, niveau);
#else
  (void)voie; (void)colle;
#endif
}

/* Relais d'un appareil flexible : seul le chauffe-eau a une sortie (D8) ; le radiateur n'a qu'une confirmation. */
static void commander_relais(int appareil, uint8_t etat)
{
  if (appareil == PILOTAGE_CHAUFFE_EAU)
  {
    if (etat) BSP_LED_On(LED_RED); else BSP_LED_Off(LED_RED);
    sortie_relais(2, etat);
  }
}

/* Batterie : le relais (D7) laisse passer le +5 V du chargeur seulement en mode « charge ».
   En « repos » et en « décharge », la batterie n'est pas rechargée. */
static void commander_batterie(uint8_t mode)
{
  sortie_relais(1, (uint8_t)(mode == 1));
}

/* Décide l'état des appareils pour la minute actuelle ; commande et confirme ce qui a changé. */
static void piloter(void)
{
  if (minute_actuelle < 0) return;
  uint8_t batterie_avant = pil.batterie;
  int premiere = (pil.minute < 0);
  uint32_t change = pilotage_evaluer(&pil, minute_actuelle);
  minute_pilotee = minute_actuelle;
  int hh = (int)((minute_actuelle % 1440) / 60), mm = (int)(minute_actuelle % 60);
  for (int a = 0; a < PILOTAGE_NB_APPAREILS; a++)
  {
    if (!(change & (1u << a))) continue;
    commander_relais(a, pil.app[a].etat);
    char topic[48], msg[8], info[64];
    if (pilotage_confirmation(&pil, a, topic, sizeof topic, msg, sizeof msg) == 0) publier(topic, msg);
    snprintf(info, sizeof info, "RELAIS %02d%02d %s %s (%s)\r\n", hh, mm, pilotage_nom(a), msg,
             pilotage_nom_origine(pil.app[a].origine));
    envoyer_message(info);
  }
  if (premiere || pil.batterie != batterie_avant)
  {
    static const char *const MODES[] = { "repos", "charge", "decharge" };
    char info[48];
    commander_batterie(pil.batterie);
    snprintf(info, sizeof info, "BATTERIE %02d%02d %s\r\n", hh, mm, MODES[pil.batterie % 3]);
    envoyer_message(info);
  }
}

/* Message MQTT reçu sur nilm/maison/cmd/+ : planning de l'EMS ou ordre de Home Assistant.
   Point d'entrée pour le pilote du ST87M01 (partie B) ; sur PC, lignes « MQTT <topic> <message> ». */
void appli_message_recu(const char *topic, const char *message)
{
  int r = pilotage_message(&pil, topic, message, minute_actuelle);
  char info[64];
  static const char *const RES[] = { "ignore", "planning ok", "ordre ok", "ordre deja recu" };
  snprintf(info, sizeof info, "RECU %s : %s\r\n", topic, r < 0 ? "REJETE" : RES[r]);
  envoyer_message(info);
  if (r == PILOTAGE_RECU_PLAN || r == PILOTAGE_RECU_ORDRE) piloter();
}

/* Essais sur PC : une ligne de texte hors trame TIC (« MQTT nilm/maison/cmd/plan 2101;R;... ») */
static void octet_ligne(uint8_t c)
{
  c &= 0x7F;
  if (c == '\r' || c == '\n' || c == 0x02 || c == 0x03)
  {
    ligne_rx[ligne_rx_n] = 0;
    if (ligne_rx_n > 5 && strncmp(ligne_rx, "MQTT ", 5) == 0)
    {
      char *topic = ligne_rx + 5, *msg = strchr(topic, ' ');
      if (msg) { *msg++ = 0; appli_message_recu(topic, msg); }
    }
    ligne_rx_n = 0;
    return;
  }
  if (ligne_rx_n < sizeof ligne_rx - 1) ligne_rx[ligne_rx_n++] = (char)c;
}

/* Une puissance datée -> NILM ; si une fenêtre est prête, le modèle tourne et le message part. */
static void puissance_vers_nilm(int32_t minute, float puissance)
{
  if (!nilm_flux_mesure(&nilm, minute, puissance)) return;
  if (nilm_etat_ia != 0)
  {
    char err[48];                                 /* modèle pas prêt : on le signale au lieu de se taire */
    snprintf(err, sizeof err, "NILM ERREUR init=%ld\r\n", (long)nilm_etat_ia);
    envoyer_message(err);
    return;
  }
  uint32_t duree;
  int err = nilm_ia_calculer(&nilm, &duree);
  if (err != 0)
  {
    nilm_erreurs++;
    char l[64];
    snprintf(l, sizeof l, "NILM ERREUR calcul=%d (npu bloque si -10)\r\n", err);
    envoyer_message(l);
    return;
  }
  nilm_duree_us = duree;
  nilm_messages++;
  char ligne[80];
#if NILM_AFFICHER_DUREE                           /* durée du calcul en fin de ligne, pour les essais */
  snprintf(ligne, sizeof ligne, "NILM %s t=%luus\r\n", nilm.message, (unsigned long)duree);
#else
  snprintf(ligne, sizeof ligne, "NILM %s\r\n", nilm.message);
#endif
  envoyer_message(ligne);
  BSP_LED_Toggle(LED_BLUE);
}

/* ------------------------------------------------------------------ interface */
void appli_init(void)
{
  tic_init(&tic);
  mesure_init(&mes, 4000, K_V, K_I, 60);
  nilm_flux_init(&nilm);
  pilotage_init(&pil);
  sortie_relais(1, 0);                     /* relais au repos tant que l'heure n'est pas connue */
  sortie_relais(2, 0);
  envoyer_message("DEMARRAGE : init du modele...\r\n");
  nilm_etat_ia = nilm_ia_init();
  {
    char l[48];
    snprintf(l, sizeof l, "DEMARRAGE : modele etat %ld\r\n", (long)nilm_etat_ia);
    envoyer_message(l);
  }
  minute_vi = nilm_minute_horodate(DEPART_HORODATE);
}

/* Interruption de l'ADC : un couple (tension, courant) toutes les 250 µs. */
void appli_echantillon(uint16_t v_brut, uint16_t i_brut)
{
  int r = mesure_echantillon(&mes, v_brut, i_brut);
  if (r == MESURE_RIEN) return;
  uint32_t t = HAL_GetTick();                     /* un bloc = 4000 échantillons = 1 s */
  if (t_bloc != 0 && t != t_bloc) cadence_hz = 4000000.0f / (float)(t - t_bloc);
  t_bloc = t;
  if (r == MESURE_MINUTE) minute_vi_prete = 1;    /* traité dans la boucle, hors interruption */
}

static void trame_tic_valide(void)
{
  BSP_LED_Toggle(LED_GREEN);
  int32_t minute = nilm_minute_horodate(tic.horodate);
  if (minute >= 0) minute_actuelle = minute;
#if SOURCE_PUISSANCE == SOURCE_TIC
  puissance_vers_nilm(minute, (float)tic.papp_va);
#else
  if (minute >= 0) minute_vi = minute;            /* une trame TIC remet l'horloge à l'heure */
#endif
}

void appli_pas(void)
{
  uint8_t octet;
  HAL_StatusTypeDef st = HAL_UART_Receive(&hcom_uart[COM1], &octet, 1, 5);
  if (st == HAL_OK)
  {
    nb_octets_recus++;
    if (tic_octet(&tic, octet) == TIC_TRAME_OK) trame_tic_valide();
    octet_ligne(octet);
  }
  else if (st == HAL_ERROR)
  {
    nb_erreurs_uart++;
    __HAL_UART_CLEAR_FLAG(&hcom_uart[COM1], UART_CLEAR_PEF | UART_CLEAR_FEF | UART_CLEAR_NEF | UART_CLEAR_OREF);
    hcom_uart[COM1].ErrorCode = HAL_UART_ERROR_NONE;
    hcom_uart[COM1].RxState = HAL_UART_STATE_READY;
  }

#if SOURCE_PUISSANCE == SOURCE_VI
  if (minute_vi_prete)
  {
    minute_vi_prete = 0;
    int32_t m = minute_vi++;                      /* minute qui vient de se terminer */
    minute_actuelle = minute_vi;
    float s = mes.s_minute, p = mes.p_minute;
    /* une ligne par minute pour l'étalonnage : U (dV), I (cA), P (W), S (VA), fp (centièmes) */
    char ligne[96];
#if CAPTEURS_REELS
    snprintf(ligne, sizeof ligne, "VI %02ld%02ld U=%ld dV I=%ld cA P=%ld W S=%ld VA fp=%ld\r\n",
             (long)((m % 1440) / 60), (long)(m % 60), (long)(mes.vrms * 10.0f), (long)(mes.irms * 100.0f),
             (long)p, (long)s, (long)(mes.fp * 100.0f));
#else
    /* essai au générateur : valeurs efficaces en millivolts sur le connecteur (A1 tension, A0 courant) */
    (void)p;
    snprintf(ligne, sizeof ligne, "VI %02ld%02ld U=%ld mV I=%ld mV fp=%ld (centiemes)\r\n",
             (long)((m % 1440) / 60), (long)(m % 60), (long)(mes.vrms * 1000.0f), (long)(mes.irms * 1000.0f),
             (long)(mes.fp * 100.0f));
#endif
    envoyer_message(ligne);
    puissance_vers_nilm(m, s);
  }
#endif

  if (minute_actuelle >= 0 && minute_actuelle != minute_pilotee) piloter();   /* une fois par minute */
}
