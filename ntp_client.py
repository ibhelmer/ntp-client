"""
Simple NTP client with a Tkinter GUI.

The program sends a standard 48-byte NTP request over UDP port 123,
parses the server response and displays the NTP time, local time,
local UDP source port, round-trip delay and estimated clock offset.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import queue
import socket
import struct
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from tkinter import messagebox, ttk


NTP_PORT = 123
NTP_PACKET_SIZE = 48
NTP_EPOCH_OFFSET = 2_208_988_800
DEFAULT_SERVER = "pool.ntp.org"
DEFAULT_TIMEOUT = 3.0


@dataclass
class NTPResult:
    server: str
    ip_address: str
    local_udp_port: int
    stratum: int
    version: int
    mode: int
    ntp_time: datetime
    local_time: datetime
    round_trip_ms: float
    clock_offset_ms: float


def ntp_timestamp_to_unix(data: bytes) -> float:
    """Convert an 8-byte NTP timestamp to Unix seconds."""
    seconds, fraction = struct.unpack("!II", data)
    return seconds - NTP_EPOCH_OFFSET + fraction / 2**32


def query_ntp(server: str, timeout: float = DEFAULT_TIMEOUT) -> NTPResult:
    """Query an NTP server and return parsed timing information."""
    server = server.strip()
    if not server:
        raise ValueError("NTP-server må ikke være tom.")

    address_info = socket.getaddrinfo(
        server,
        NTP_PORT,
        type=socket.SOCK_DGRAM,
    )
    if not address_info:
        raise OSError(f"Kunne ikke slå serveren '{server}' op.")

    family, socktype, proto, _, sockaddr = address_info[0]

    # LI = 0, VN = 4, Mode = 3 (client)
    request = bytearray(NTP_PACKET_SIZE)
    request[0] = 0x23

    with socket.socket(family, socktype, proto) as sock:
        sock.settimeout(timeout)

        t1 = time.time()
        sock.sendto(request, sockaddr)

        # After the first send, the OS has selected/bound the ephemeral
        # local UDP source port used for this NTP request.
        local_udp_port = sock.getsockname()[1]

        response, remote_address = sock.recvfrom(512)
        t4 = time.time()

    if len(response) < NTP_PACKET_SIZE:
        raise ValueError(
            f"Ugyldigt NTP-svar: forventede mindst 48 bytes, modtog {len(response)}."
        )

    first_byte = response[0]
    version = (first_byte >> 3) & 0x07
    mode = first_byte & 0x07
    stratum = response[1]

    if mode not in (4, 5):
        raise ValueError(f"Uventet NTP-mode i svaret: {mode}.")
    if stratum == 0:
        raise ValueError("NTP-serveren returnerede et Kiss-o'-Death/ugyldigt svar.")

    # Receive timestamp (T2) and transmit timestamp (T3).
    t2 = ntp_timestamp_to_unix(response[32:40])
    t3 = ntp_timestamp_to_unix(response[40:48])

    # Standard NTP delay/offset calculations.
    round_trip = (t4 - t1) - (t3 - t2)
    clock_offset = ((t2 - t1) + (t3 - t4)) / 2

    corrected_unix_time = t4 + clock_offset
    ntp_utc = datetime.fromtimestamp(corrected_unix_time, tz=timezone.utc)
    local_time = ntp_utc.astimezone()

    return NTPResult(
        server=server,
        ip_address=remote_address[0],
        local_udp_port=local_udp_port,
        stratum=stratum,
        version=version,
        mode=mode,
        ntp_time=ntp_utc,
        local_time=local_time,
        round_trip_ms=round_trip * 1000,
        clock_offset_ms=clock_offset * 1000,
    )


class NTPClientGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Simple NTP Client")
        self.root.resizable(False, False)

        self.results: queue.Queue[tuple[str, object]] = queue.Queue()

        self.server_var = tk.StringVar(value=DEFAULT_SERVER)
        self.status_var = tk.StringVar(value="Klar")
        self.utc_var = tk.StringVar(value="-")
        self.local_var = tk.StringVar(value="-")
        self.ip_var = tk.StringVar(value="-")
        self.source_port_var = tk.StringVar(value="-")
        self.stratum_var = tk.StringVar(value="-")
        self.delay_var = tk.StringVar(value="-")
        self.offset_var = tk.StringVar(value="-")

        self._build_ui()
        self.root.after(100, self._process_results)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="NTP-server:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 12)
        )

        server_entry = ttk.Entry(main, textvariable=self.server_var, width=32)
        server_entry.grid(row=0, column=1, sticky="ew", pady=(0, 12))
        server_entry.bind("<Return>", lambda _event: self.start_query())

        self.query_button = ttk.Button(
            main,
            text="Hent tid",
            command=self.start_query,
        )
        self.query_button.grid(row=0, column=2, padx=(8, 0), pady=(0, 12))

        values = [
            ("UTC fra NTP:", self.utc_var),
            ("Lokal tid:", self.local_var),
            ("Server-IP:", self.ip_var),
            ("Udgående UDP-kildeport:", self.source_port_var),
            ("Destination UDP-port:", tk.StringVar(value=str(NTP_PORT))),
            ("Stratum:", self.stratum_var),
            ("Round-trip:", self.delay_var),
            ("Ur-afvigelse:", self.offset_var),
        ]

        for row, (label_text, variable) in enumerate(values, start=1):
            ttk.Label(main, text=label_text).grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=3
            )
            ttk.Label(main, textvariable=variable).grid(
                row=row, column=1, columnspan=2, sticky="w", pady=3
            )

        ttk.Separator(main).grid(
            row=len(values) + 1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 8),
        )

        ttk.Label(main, textvariable=self.status_var).grid(
            row=len(values) + 2,
            column=0,
            columnspan=3,
            sticky="w",
        )

        server_entry.focus()

    def start_query(self) -> None:
        server = self.server_var.get().strip()
        if not server:
            messagebox.showwarning("Manglende server", "Indtast en NTP-server.")
            return

        self.query_button.config(state="disabled")
        self.status_var.set(f"Kontakter {server} ...")

        thread = threading.Thread(
            target=self._worker,
            args=(server,),
            daemon=True,
        )
        thread.start()

    def _worker(self, server: str) -> None:
        try:
            result = query_ntp(server)
            self.results.put(("ok", result))
        except Exception as exc:
            self.results.put(("error", exc))

    def _process_results(self) -> None:
        try:
            while True:
                result_type, payload = self.results.get_nowait()

                if result_type == "ok":
                    self._show_result(payload)
                else:
                    self._show_error(payload)
        except queue.Empty:
            pass

        self.root.after(100, self._process_results)

    def _show_result(self, result: object) -> None:
        assert isinstance(result, NTPResult)

        utc_text = (
            f"{result.ntp_time.strftime('%Y-%m-%d %H:%M:%S')}."
            f"{result.ntp_time.microsecond // 1000:03d} UTC"
        )
        local_text = (
            f"{result.local_time.strftime('%Y-%m-%d %H:%M:%S')}."
            f"{result.local_time.microsecond // 1000:03d} "
            f"{result.local_time.tzname() or ''}"
        ).strip()

        self.utc_var.set(utc_text)
        self.local_var.set(local_text)
        self.ip_var.set(result.ip_address)
        self.source_port_var.set(f"UDP/{result.local_udp_port}")
        self.stratum_var.set(f"{result.stratum} (NTP v{result.version}, mode {result.mode})")
        self.delay_var.set(f"{result.round_trip_ms:.2f} ms")
        self.offset_var.set(f"{result.clock_offset_ms:+.2f} ms")
        self.status_var.set(f"Senest opdateret: {datetime.now().strftime('%H:%M:%S')}")
        self.query_button.config(state="normal")

    def _show_error(self, error: object) -> None:
        self.status_var.set("Fejl")
        self.query_button.config(state="normal")
        messagebox.showerror("NTP-fejl", str(error))


def main() -> None:
    root = tk.Tk()
    NTPClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
