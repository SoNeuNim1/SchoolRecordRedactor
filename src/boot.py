"""Frozen Windows executable entrypoint, v4.0.1.
Copyright (C) 2026 소느님. SPDX-License-Identifier: AGPL-3.0-only.

This wrapper is only a safe GUI startup boundary.
"""
from __future__ import annotations
import sys
import traceback


def main():
    try:
        import tkinter as tk
        from tkinter import messagebox
        import fitz
        from app import SchoolRedactor
        if '--check-env' in sys.argv:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo('실행 환경 점검',
                '실행에 필요한 Python 런타임 및 PDF 라이브러리가 정상적으로 포함되어 있습니다.\n'
                'PyMuPDF: ' + str(fitz.VersionBind))
            root.destroy()
            return
        root = tk.Tk()
        SchoolRedactor(root)
        root.mainloop()
    except Exception as exc:
        details = ''.join(traceback.format_exception_only(type(exc), exc)).strip()
        message = ('프로그램을 시작할 수 없습니다.\n\n' + details +
                   '\n\n오류 화면을 캡처하여 제작자에게 문의해 주세요.')
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('생기부 자동 삭제 실행 오류', message)
            root.destroy()
        except Exception:
            print(message, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
