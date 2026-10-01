//+------------------------------------------------------------------+
//| NvmDisegniGrafico.mq5 - la stessa cosa del servizio NvmDisegni,    |
//| come indicatore: trascinato su un grafico qualsiasi disegna su     |
//| tutti i grafici aperti. Serve solo se il servizio non parte.       |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_plots 0
#property copyright "nvmfinancebot"
#property version   "3.00"
#include "NvmDisegni.mqh"

int OnInit()
  {
   EventSetTimer(2);
   NvmAggiorna(false, "indicatore");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int motivo)
  {
   EventKillTimer();
   NvmPulisciTutto();
  }

void OnTimer()
  {
   NvmAggiorna(false, "indicatore");
   NvmFoto(false, "indicatore");
  }

int OnCalculate(const int rates_total, const int prev_calculated, const int begin, const double &price[])
  {
   return(rates_total);
  }
