//+------------------------------------------------------------------+
//| NvmDisegni.mq5 - servizio: i disegni del bot su tutti i grafici    |
//| Si avvia una volta sola: Navigatore -> Servizi -> NVM ->          |
//| NvmDisegni -> tasto destro -> Avvia. MT5 lo riavvia da solo.      |
//+------------------------------------------------------------------+
#property service
#property copyright "nvmfinancebot"
#property version   "1.00"
#include "NvmDisegni.mqh"

void OnStart()
  {
   while(!IsStopped())
     {
      NvmAggiorna(true);
      Sleep(2000);
     }
   NvmPulisciTutto();
  }
