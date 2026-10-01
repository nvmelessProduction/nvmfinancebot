//+------------------------------------------------------------------+
//| NvmDisegni.mqh - i disegni del bot sul grafico di MT5              |
//| Il bot (vivo.py) scrive Common\Files\nvm_disegni.csv; qui si legge |
//| e si disegna su ogni grafico aperto dello strumento giusto.        |
//| Una riga: gruppo;simbolo;tipo;t1;p1;t2;p2;colore;stile;spessore;testo|
//| tipo: linea, rettangolo, testo, su, giu, verticale, apri           |
//| t1,t2: ora del server (secondi); colore: "R,G,B"                  |
//+------------------------------------------------------------------+
#define NVM_FILE     "nvm_disegni.csv"
#define NVM_STATO    "nvm_disegni_stato.txt"
#define NVM_VERSIONE "3"
#define NVM_PREFISSO "NVM_"

datetime nvm_modifica = 0;
long     nvm_dimensione = -1;
string   nvm_aperti[];
int      nvm_grafici = -1;
datetime nvm_battito = 0;
datetime nvm_disegnato = 0;
int      nvm_oggetti = 0;
int      nvm_errori = 0;
int      nvm_ultimo_errore = 0;

// Ogni oggetto creato o fallito si conta: il bot lo legge nel file di stato e lo dice su Telegram.
bool NvmConta(const bool fatto)
  {
   if(fatto)
      nvm_oggetti++;
   else
     {
      nvm_errori++;
      nvm_ultimo_errore = GetLastError();
     }
   return(fatto);
  }

int NvmContaGrafici()
  {
   int n = 0;
   long c = ChartFirst();
   while(c >= 0)
     {
      n++;
      c = ChartNext(c);
     }
   return(n);
  }

// Il battito: ogni 30 secondi il programma scrive che e' vivo e com'e' andato l'ultimo disegno.
void NvmBattito(const string tipo)
  {
   if(TimeLocal() - nvm_battito < 30)
      return;
   int f = FileOpen(NVM_STATO, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(f == INVALID_HANDLE)
      return;
   FileWriteString(f, tipo + ";" + NVM_VERSIONE + ";" + IntegerToString((long)TimeGMT()) + ";" +
                   IntegerToString(NvmContaGrafici()) + ";" + IntegerToString(nvm_oggetti) + ";" +
                   IntegerToString(nvm_errori) + ";" + IntegerToString(nvm_ultimo_errore) + "\r\n");
   FileClose(f);
   nvm_battito = TimeLocal();
  }

// Il cartello in alto a sinistra su ogni grafico: si vede subito che i disegni sono accesi.
void NvmCartello(const long c)
  {
   string nome = NVM_PREFISSO + "cartello";
   if(!NvmConta(ObjectCreate(c, nome, OBJ_LABEL, 0, 0, 0)))
      return;
   ObjectSetInteger(c, nome, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(c, nome, OBJPROP_XDISTANCE, 8);
   ObjectSetInteger(c, nome, OBJPROP_YDISTANCE, 22);
   ObjectSetString(c, nome, OBJPROP_TEXT, "NVM: disegni accesi (aggiornati " + TimeToString(nvm_disegnato, TIME_MINUTES) + ")");
   ObjectSetString(c, nome, OBJPROP_FONT, "Arial");
   ObjectSetInteger(c, nome, OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(c, nome, OBJPROP_COLOR, clrGold);
   ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
  }

bool NvmGiaAperto(const string gruppo)
  {
   for(int i = 0; i < ArraySize(nvm_aperti); i++)
      if(nvm_aperti[i] == gruppo)
         return(true);
   return(false);
  }

bool NvmCeGrafico(const string simbolo)
  {
   long c = ChartFirst();
   while(c >= 0)
     {
      if(ChartSymbol(c) == simbolo)
         return(true);
      c = ChartNext(c);
     }
   return(false);
  }

void NvmPulisciTutto()
  {
   long c = ChartFirst();
   while(c >= 0)
     {
      ObjectsDeleteAll(c, NVM_PREFISSO);
      ChartRedraw(c);
      c = ChartNext(c);
     }
  }

void NvmEtichetta(const long c, const string nome, const datetime t, const double p, const color colore,
                  const string testo, const ENUM_ANCHOR_POINT ancora)
  {
   if(testo == "")
      return;
   if(!NvmConta(ObjectCreate(c, nome, OBJ_TEXT, 0, t, p)))
      return;
   ObjectSetString(c, nome, OBJPROP_TEXT, testo);
   ObjectSetString(c, nome, OBJPROP_FONT, "Arial");
   ObjectSetInteger(c, nome, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(c, nome, OBJPROP_COLOR, colore);
   ObjectSetInteger(c, nome, OBJPROP_ANCHOR, ancora);
   ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
  }

void NvmDisegnaRiga(const long c, const string nome, const string &p[])
  {
   string   tipo = p[2];
   datetime t1 = (datetime)StringToInteger(p[3]);
   double   p1 = StringToDouble(p[4]);
   datetime t2 = (datetime)StringToInteger(p[5]);
   double   p2 = StringToDouble(p[6]);
   color    colore = StringToColor(p[7]);
   int      stile = (int)StringToInteger(p[8]);
   int      spessore = (int)StringToInteger(p[9]);
   string   testo = p[10];
   ENUM_LINE_STYLE st = (stile == 1 ? STYLE_DASH : (stile == 2 ? STYLE_DOT : STYLE_SOLID));
   if(tipo == "linea")
     {
      if(NvmConta(ObjectCreate(c, nome, OBJ_TREND, 0, t1, p1, t2, p2)))
        {
         ObjectSetInteger(c, nome, OBJPROP_COLOR, colore);
         ObjectSetInteger(c, nome, OBJPROP_STYLE, st);
         ObjectSetInteger(c, nome, OBJPROP_WIDTH, spessore);
         ObjectSetInteger(c, nome, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
         ObjectSetString(c, nome, OBJPROP_TOOLTIP, testo);
        }
      NvmEtichetta(c, nome + "_t", t1, p1, colore, testo, ANCHOR_LEFT_LOWER);
     }
   else if(tipo == "rettangolo")
     {
      if(NvmConta(ObjectCreate(c, nome, OBJ_RECTANGLE, 0, t1, p1, t2, p2)))
        {
         ObjectSetInteger(c, nome, OBJPROP_COLOR, colore);
         ObjectSetInteger(c, nome, OBJPROP_FILL, true);
         ObjectSetInteger(c, nome, OBJPROP_BACK, true);
         ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
         ObjectSetString(c, nome, OBJPROP_TOOLTIP, testo);
        }
      NvmEtichetta(c, nome + "_t", t1, MathMax(p1, p2), clrDimGray, testo, ANCHOR_LEFT_LOWER);
     }
   else if(tipo == "testo")
      NvmEtichetta(c, nome, t1, p1, colore, testo, ANCHOR_LEFT_LOWER);
   else if(tipo == "su" || tipo == "giu")
     {
      if(NvmConta(ObjectCreate(c, nome, (tipo == "su" ? OBJ_ARROW_BUY : OBJ_ARROW_SELL), 0, t1, p1)))
        {
         ObjectSetInteger(c, nome, OBJPROP_COLOR, colore);
         ObjectSetInteger(c, nome, OBJPROP_WIDTH, 2);
         ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
        }
      NvmEtichetta(c, nome + "_t", t1, p1, colore, testo, (tipo == "su" ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER));
     }
   else if(tipo == "verticale")
     {
      if(NvmConta(ObjectCreate(c, nome, OBJ_VLINE, 0, t1, 0)))
        {
         ObjectSetInteger(c, nome, OBJPROP_COLOR, colore);
         ObjectSetInteger(c, nome, OBJPROP_STYLE, st);
         ObjectSetInteger(c, nome, OBJPROP_WIDTH, spessore);
         ObjectSetInteger(c, nome, OBJPROP_BACK, true);
         ObjectSetInteger(c, nome, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(c, nome, OBJPROP_HIDDEN, true);
         ObjectSetString(c, nome, OBJPROP_TEXT, testo);
         ObjectSetString(c, nome, OBJPROP_TOOLTIP, testo);
        }
     }
  }

// Rilegge il file se e' cambiato (o se si e' aperto o chiuso un grafico) e ridisegna tutto. `apri`:
// si possono aprire i grafici mancanti (solo il servizio: gli indicatori non possono). `tipo`:
// "servizio" o "indicatore", per il file di stato.
void NvmAggiorna(const bool apri, const string tipo)
  {
   NvmBattito(tipo);
   if(!FileIsExist(NVM_FILE, FILE_COMMON))
      return;
   datetime modifica = (datetime)FileGetInteger(NVM_FILE, FILE_MODIFY_DATE, true);
   long dimensione = FileGetInteger(NVM_FILE, FILE_SIZE, true);
   int grafici = NvmContaGrafici();
   if(modifica == nvm_modifica && dimensione == nvm_dimensione && grafici == nvm_grafici)
      return;
   nvm_grafici = grafici;
   int f = FileOpen(NVM_FILE, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(f == INVALID_HANDLE)
      return;
   string righe[];
   int n = 0;
   while(!FileIsEnding(f))
     {
      string r = FileReadString(f);
      StringTrimRight(r);
      StringTrimLeft(r);
      if(StringLen(r) < 5)
         continue;
      ArrayResize(righe, n + 1);
      righe[n++] = r;
     }
   FileClose(f);
   nvm_modifica = modifica;
   nvm_dimensione = dimensione;
   nvm_oggetti = 0;
   nvm_errori = 0;
   nvm_ultimo_errore = 0;
   nvm_disegnato = TimeLocal();
   NvmPulisciTutto();
   for(int i = 0; i < n; i++)
     {
      string p[];
      if(StringSplit(righe[i], ';', p) < 11)
         continue;
      if(p[2] == "apri")
        {
         if(apri && !NvmGiaAperto(p[0]) && !NvmCeGrafico(p[1]))
           {
            SymbolSelect(p[1], true);
            ChartOpen(p[1], PERIOD_H1);
           }
         int k = ArraySize(nvm_aperti);
         ArrayResize(nvm_aperti, k + 1);
         nvm_aperti[k] = p[0];
         continue;
        }
      long c = ChartFirst();
      while(c >= 0)
        {
         if(ChartSymbol(c) == p[1])
            NvmDisegnaRiga(c, NVM_PREFISSO + p[0] + "_" + IntegerToString(i), p);
         c = ChartNext(c);
        }
     }
   long c = ChartFirst();
   while(c >= 0)
     {
      NvmCartello(c);
      ChartRedraw(c);
      c = ChartNext(c);
     }
   nvm_battito = 0;
   NvmBattito(tipo);
  }

ENUM_TIMEFRAMES NvmPeriodo(const string p)
  {
   if(p == "M15") return(PERIOD_M15);
   if(p == "H4")  return(PERIOD_H4);
   if(p == "D1")  return(PERIOD_D1);
   if(p == "W1")  return(PERIOD_W1);
   if(p == "MN")  return(PERIOD_MN1);
   return(PERIOD_H1);
  }

// Le foto del grafico coi disegni, per vederli dal telefono su Telegram (le app di MT5 per il telefono
// non mostrano i disegni dei programmi). Il bot chiede una foto con un file Common\Files\nvm_foto_ID.req
// ("simbolo;periodo"); qui si apre il grafico (solo il servizio), si disegna, si fotografa in
// MQL5\Files\nvm_foto_ID.png e si richiude il grafico aperto apposta.
void NvmFoto(const bool apri, const string tipo)
  {
   string nomi[];
   string nome;
   long h = FileFindFirst("nvm_foto_*.req", nome, FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   do
     {
      int k = ArraySize(nomi);
      ArrayResize(nomi, k + 1);
      nomi[k] = nome;
     }
   while(FileFindNext(h, nome));
   FileFindClose(h);
   for(int i = 0; i < ArraySize(nomi); i++)
     {
      string r = "";
      int f = FileOpen(nomi[i], FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
      if(f != INVALID_HANDLE)
        {
         r = FileReadString(f);
         FileClose(f);
        }
      FileDelete(nomi[i], FILE_COMMON);
      StringTrimRight(r);
      string p[];
      if(StringSplit(r, ';', p) < 2)
         continue;
      string id = StringSubstr(nomi[i], 9, StringLen(nomi[i]) - 13);
      long c = -1;
      bool mio = false;
      if(apri)
        {
         SymbolSelect(p[0], true);
         c = ChartOpen(p[0], NvmPeriodo(p[1]));
         mio = (c > 0);
        }
      if(c <= 0)
        {
         c = ChartFirst();
         while(c >= 0 && ChartSymbol(c) != p[0])
            c = ChartNext(c);
        }
      if(c < 0)
         continue;
      if(mio)
        {
         ChartSetInteger(c, CHART_AUTOSCROLL, true);
         ChartSetInteger(c, CHART_SHIFT, true);
         ChartSetInteger(c, CHART_SCALE, 3);
         Sleep(3000);
        }
      nvm_grafici = -1;
      nvm_modifica = 0;
      NvmAggiorna(false, tipo);
      ChartRedraw(c);
      if(mio)
         Sleep(1500);
      ChartScreenShot(c, "nvm_foto_" + id + ".png", 1280, 800, ALIGN_RIGHT);
      if(mio)
         ChartClose(c);
     }
  }
