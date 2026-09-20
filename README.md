# Simple NTP Client

Et lille NTP-klientprogram skrevet i Python med Tkinter-GUI.

Programmet sender en almindelig NTP-forespørgsel over UDP port 123 og viser:

- NTP-tid i UTC
- lokal tid
- NTP-serverens IP-adresse
- stratum
- round-trip delay
- estimeret forskel mellem systemuret og NTP-serveren

## Krav

- Python 3.10 eller nyere anbefales
- Tkinter skal være installeret
- Netværket skal tillade UDP trafik til port 123

Der bruges ingen eksterne Python-pakker.

## Start programmet

```bash
python ntp_client.py
```

På nogle Linux-distributioner skal Tkinter installeres separat, f.eks. på Ubuntu/Debian:

```bash
sudo apt install python3-tk
```

## Standardserver

Programmet bruger som standard:

```
pool.ntp.org
```

Du kan skrive en anden NTP-server i GUI'en, f.eks.:

```
time.cloudflare.com
time.google.com
dk.pool.ntp.org
```

## Hvordan virker det?

Klienten sender en 48-byte NTP-pakke med:

- NTP version 4
- client mode
- UDP destination port 123

Fra serversvaret læses blandt andet receive timestamp og transmit timestamp.

Programmet bruger derefter de klassiske NTP-beregninger:

```
delay  = (T4 - T1) - (T3 - T2)

offset = ((T2 - T1) + (T3 - T4)) / 2
```

hvor:

- T1 = tidspunkt hvor klienten sender forespørgslen
- T2 = tidspunkt hvor serveren modtager forespørgslen
- T3 = tidspunkt hvor serveren sender svaret
- T4 = tidspunkt hvor klienten modtager svaret

## Bemærkning

Programmet ændrer ikke computerens systemur. Det måler kun tiden og viser den estimerede afvigelse.

Det gør projektet velegnet som et simpelt undervisningseksempel på UDP, applikationslagsprotokoller og tidsprotokollen NTP.
