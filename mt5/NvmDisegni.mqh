//+------------------------------------------------------------------+
//| NvmDisegni.mqh - i disegni del bot sul grafico di MT5              |
//| Il bot (vivo.py) scrive Common\Files\nvm_disegni.csv; qui si legge |
//| e si disegna su ogni grafico aperto dello strumento giusto.        |
//| Una riga: gruppo;simbolo;tipo;t1;p1;t2;p2;colore;stile;spessore;testo|
//| tipo: linea, rettangolo, testo, su, giu, verticale, apri           |
//| t1,t2: ora del server (secondi); colore: "R,G,B"                  |
//+------------------------------------------------------------------+
#define NVM_FILE     "nvm_disegni.csv"
#define NVM_PREFISSO "NVM_"

datetime nvm_modifica = 0;
long     nvm_dimensione = -1;
string   nvm_aperti[];

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
   if(!ObjectCreate(c, nome, OBJ_TEXT, 0, t, p))
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
      if(ObjectCreate(c, nome, OBJ_TREND, 0, t1, p1, t2, p2))
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
      if(ObjectCreate(c, nome, OBJ_RECTANGLE, 0, t1, p1, t2, p2))
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
      if(ObjectCreate(c, nome, (tipo == "su" ? OBJ_ARROW_BUY : OBJ_ARROW_SELL), 0, t1, p1))
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
      if(ObjectCreate(c, nome, OBJ_VLINE, 0, t1, 0))
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

// Rilegge il file se e' cambiato e ridisegna tutto. `apri`: si possono aprire i grafici mancanti
// (solo il servizio: gli indicatori non possono).
void NvmAggiorna(const bool apri)
  {
   if(!FileIsExist(NVM_FILE, FILE_COMMON))
      return;
   datetime modifica = (datetime)FileGetInteger(NVM_FILE, FILE_MODIFY_DATE, true);
   long dimensione = FileGetInteger(NVM_FILE, FILE_SIZE, true);
   if(modifica == nvm_modifica && dimensione == nvm_dimensione)
      return;
   int f = FileOpen(NVM_FILE, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(f == INVALID_HANDLE)
      return;
   string righe[];
   int n = 0;
   while(!FileIsEnding(f))
     {
      string r = FileReadString(f);
      if(StringLen(r) < 5)
         continue;
      ArrayResize(righe, n + 1);
      righe[n++] = r;
     }
   FileClose(f);
   nvm_modifica = modifica;
   nvm_dimensione = dimensione;
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
      ChartRedraw(c);
      c = ChartNext(c);
     }
  }
