"""SchoolRecordRedactor GUI. Copyright (C) 2026 소느님.
SPDX-License-Identifier: AGPL-3.0-only.

Choose PDF files -> automatic preview -> batch anonymize locally."""
from __future__ import annotations
import base64
import queue
import threading
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import fitz

from redactor_core import Options, SUFFIX, anonymize_pdf, destination_for, inspect_file, is_generated_name, preview_page

BG='#f3f6fb'; NAVY='#17283e'; BLUE='#1e61b5'

class SchoolRedactor:
    def __init__(self,root:tk.Tk):
        self.root=root
        root.title('생기부 개인정보 자동 삭제 v4.0.1 | 공개용 · 모의면접용')
        root.geometry('1240x840')
        root.minsize(940,660)
        root.configure(bg=BG)
        self.files=[]
        self.busy=False
        self.preview_source=None
        self.preview_index=0
        self.photo=None
        self.after_id=None
        self.show_redacted=tk.BooleanVar(value=True)
        self.keep_student_id=tk.BooleanVar(value=True)
        self.keep_name=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='① PDF 파일 또는 폴더 선택 → ② 결과 미리보기 → ③ 일괄 저장')
        self.preview_status=tk.StringVar(value='PDF를 선택하면 개인정보가 지워진 모습을 미리 보여줍니다.')
        self.folder_label=tk.StringVar(value='저장 위치: 원본 폴더 안의 「면접용_결과」')
        self.target_dir=None
        self.events=queue.Queue()
        self.render_setup()
        self.install_legal_menu()
        self.root.after(100,self.poll)
        self.root.protocol('WM_DELETE_WINDOW',self.close)

    def options(self):
        return Options(keep_student_id=self.keep_student_id.get(),keep_name=self.keep_name.get())

    def render_setup(self):
        s=ttk.Style()
        if 'clam' in s.theme_names():s.theme_use('clam')
        s.configure('TButton',padding=(11,8),font=('맑은 고딕',10))
        s.configure('Treeview',font=('맑은 고딕',10),rowheight=28)
        s.configure('Treeview.Heading',font=('맑은 고딕',10,'bold'))
        header=tk.Frame(self.root,bg='white',padx=20,pady=14);header.pack(fill='x')
        tk.Label(header,text='생기부 개인정보 자동 삭제',font=('맑은 고딕',18,'bold'),bg='white',fg=NAVY).pack(side='left')
        tk.Label(header,text='클릭만으로 여러 PDF 처리 · 표 선 보존 · 인터넷 전송 없음',bg='white',fg='#5b6e83',font=('맑은 고딕',10)).pack(side='left',padx=(16,0))
        toolbar=tk.Frame(self.root,bg=BG,padx=16,pady=10);toolbar.pack(fill='x')
        ttk.Button(toolbar,text='① 여러 PDF 추가',command=self.pick_files).pack(side='left',padx=(0,6))
        ttk.Button(toolbar,text='폴더에서 PDF 추가',command=self.pick_folder).pack(side='left',padx=6)
        ttk.Button(toolbar,text='선택 제거',command=self.remove_files).pack(side='left',padx=6)
        ttk.Button(toolbar,text='목록 비우기',command=self.clear_files).pack(side='left',padx=6)
        ttk.Button(toolbar,text='③ 전체 자동 처리 · 저장',command=self.save_batch).pack(side='right',padx=6)
        ttk.Button(toolbar,text='저장 폴더 변경',command=self.choose_output).pack(side='right',padx=6)

        panel=tk.Frame(self.root,bg='white',padx=17,pady=11);panel.pack(fill='x',padx=16,pady=(0,9))
        tk.Label(panel,text='면접관 확인용 하단 식별정보',font=('맑은 고딕',10,'bold'),bg='white',fg=NAVY).pack(side='left')
        for label,var in [('학번 유지',self.keep_student_id),('이름 유지',self.keep_name)]:
            tk.Checkbutton(panel,text=label,variable=var,bg='white',fg=NAVY,command=self.preview,
                           activebackground='white',font=('맑은 고딕',10)).pack(side='left',padx=7)
        tk.Label(panel,text='인적사항·학교명·최하단 출력정보 자동 삭제',bg='white',fg='#67788c').pack(side='right')

        split=tk.PanedWindow(self.root,sashwidth=6,orient=tk.HORIZONTAL,bg=BG,bd=0)
        split.pack(fill='both',expand=True,padx=16,pady=(0,5))
        left=tk.Frame(split,bg='white',padx=12,pady=12)
        right=tk.Frame(split,bg='white',padx=12,pady=12)
        split.add(left,minsize=350,width=500);split.add(right,minsize=420)
        tk.Label(left,text='작업 파일 목록',font=('맑은 고딕',12,'bold'),bg='white',fg=NAVY).pack(anchor='w',pady=(0,8))
        wrap=tk.Frame(left,bg='white');wrap.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(wrap,columns=('filename','pages','state'),show='headings',selectmode='extended')
        self.tree.heading('filename',text='PDF 파일명')
        self.tree.heading('pages',text='장수')
        self.tree.heading('state',text='상태')
        self.tree.column('filename',width=280,minwidth=110,stretch=True)
        self.tree.column('pages',width=52,minwidth=45,anchor='center',stretch=False)
        self.tree.column('state',width=92,minwidth=75,anchor='center',stretch=False)
        scroll=ttk.Scrollbar(wrap,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.selected_file)
        tk.Label(left,text='원본은 그대로 유지됩니다. 오류가 나는 파일은 건너뜁니다.\n이미 (모의면접용)으로 만든 파일은 추가하지 않습니다.',
                 bg='white',fg='#64748b',justify='left',font=('맑은 고딕',9),pady=9).pack(anchor='w')

        viewbar=tk.Frame(right,bg='white');viewbar.pack(fill='x',pady=(0,8))
        tk.Label(viewbar,text='② 자동 익명화 미리보기',font=('맑은 고딕',12,'bold'),bg='white',fg=NAVY).pack(side='left')
        ttk.Button(viewbar,text='▶',width=3,command=lambda:self.page_change(1)).pack(side='right',padx=2)
        ttk.Button(viewbar,text='◀',width=3,command=lambda:self.page_change(-1)).pack(side='right',padx=2)
        self.page_text=tk.Label(viewbar,text='0 / 0쪽',bg='white',fg=NAVY)
        self.page_text.pack(side='right',padx=10)
        tk.Checkbutton(viewbar,text='삭제 후 보기',variable=self.show_redacted,command=self.preview,
                       bg='white',activebackground='white').pack(side='right',padx=6)
        canvas_wrap=tk.Frame(right,bg='#e1e8f0');canvas_wrap.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(canvas_wrap,bg='#e1e8f0',highlightthickness=0)
        cscroll=ttk.Scrollbar(canvas_wrap,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=cscroll.set)
        self.canvas.pack(side='left',fill='both',expand=True);cscroll.pack(side='right',fill='y')
        self.canvas.bind('<Configure>',self.resize)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
        tk.Label(right,textvariable=self.preview_status,bg='white',fg='#53667f',font=('맑은 고딕',9),
                 wraplength=530,justify='left',pady=7).pack(fill='x')
        bottom=tk.Frame(self.root,bg='white',padx=16,pady=9);bottom.pack(fill='x')
        tk.Label(bottom,textvariable=self.folder_label,fg='#53667f',bg='white',anchor='w').pack(fill='x')
        row=tk.Frame(bottom,bg='white');row.pack(fill='x',pady=(4,0))
        tk.Label(row,textvariable=self.status,bg='white',fg=NAVY,anchor='w').pack(side='left',fill='x',expand=True)
        self.progress=ttk.Progressbar(row,mode='determinate',length=160)
        self.progress.pack(side='right')
        # Credits belong only to the application UI, never to any exported PDF.
        self.credits_label=tk.Label(
            bottom, text='제작 소느님  |  문의: soneunim1@gmail.com  |  AGPL-3.0',
            bg='white', fg='#718096', font=('맑은 고딕',9), anchor='e'
        )
        self.credits_label.pack(side='bottom', fill='x', pady=(7,0))
        tk.Label(bottom, text='주의: 자동 삭제가 완전한 익명화를 보증하지 않습니다. 생성된 PDF 전체를 직접 확인하세요.',
                 bg='white',fg='#a34d19',font=('맑은 고딕',9),anchor='w').pack(fill='x',pady=(6,0))

    @staticmethod
    def resource_root():
        """Works with source checkout and PyInstaller --onefile/--onedir."""
        return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))

    def install_legal_menu(self):
        menubar=tk.Menu(self.root)
        help_menu=tk.Menu(menubar,tearoff=0)
        help_menu.add_command(label='프로그램 정보 (About)',command=self.show_about)
        help_menu.add_command(label='오픈소스 라이선스',command=self.show_licenses)
        menubar.add_cascade(label='도움말',menu=help_menu)
        self.root.configure(menu=menubar)

    def show_about(self):
        messagebox.showinfo('SchoolRecordRedactor 정보',
            'SchoolRecordRedactor v4.0.1\n\n'
            '제작 소느님\n문의: soneunim1@gmail.com\n\n'
            'Copyright (C) 2026 소느님\nAGPL-3.0-only\n'
            '본 프로그램은 무료 소프트웨어이며 재배포 및 수정이 가능합니다.\n'
            '관련 조건은 [도움말] > [오픈소스 라이선스]를 확인하세요.\n\n'
            '이 프로그램은 어떠한 보증도 제공하지 않습니다.\n'
            '교육부·교육청·NEIS 공식 프로그램이 아닙니다.\n'
            'PDF 삭제 결과는 반드시 사람이 검토해야 합니다.')

    def show_licenses(self):
        root=self.resource_root()
        notice=root/'LICENSES'/'THIRD_PARTY_NOTICES.txt'
        if not notice.exists():
            notice=root/'LICENSES'/'SOURCE_BUILD_NOTICES.txt'
        chunks=['SchoolRecordRedactor v4.0.1\nCopyright (C) 2026 소느님\n'
                'License: AGPL-3.0-only\nNO WARRANTY.\n\n'
                '배포판과 동일 버전의 대응 소스코드 및 제3자 소스는 배포 페이지에서 제공됩니다.\n']
        for file in (notice,root/'LICENSE',
                     root/'LICENSES'/'Python-PSF-LICENSE.txt',
                     root/'LICENSES'/'Tcl-license.terms',
                     root/'LICENSES'/'Tk-license.terms',
                     root/'LICENSES'/'PyInstaller-COPYING.txt',
                     root/'LICENSES'/'PyMuPDF-COPYING.txt'):
            if file.exists():
                chunks.append('\n\n--- '+file.name+' ---\n'+file.read_text(encoding='utf-8',errors='replace'))
        popup=tk.Toplevel(self.root)
        popup.title('오픈소스 라이선스 및 저작권')
        popup.geometry('780x600');popup.minsize(500,360)
        wrap=tk.Frame(popup,padx=12,pady=12);wrap.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(wrap);scroll.pack(side='right',fill='y')
        text=tk.Text(wrap,wrap='word',yscrollcommand=scroll.set,
                     font=('Consolas',10),background='#fbfcff')
        text.pack(side='left',fill='both',expand=True)
        scroll.configure(command=text.yview)
        text.insert('1.0',''.join(chunks));text.configure(state='disabled')

    def pick_files(self):
        if self.busy:return
        picked=filedialog.askopenfilenames(title='생활기록부 PDF 여러 개 선택',filetypes=[('PDF 파일','*.pdf')])
        if picked:self.add_files([Path(p) for p in picked])

    def pick_folder(self):
        if self.busy:return
        folder=filedialog.askdirectory(title='생활기록부 PDF 폴더 선택')
        if folder:
            paths=[p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower()=='.pdf']
            if paths:self.add_files(sorted(paths,key=lambda p:p.name.casefold()))
            else:messagebox.showinfo('PDF 없음','선택한 폴더에 PDF 파일이 없습니다.')

    def add_files(self,paths):
        originals=set(str(p.resolve()).casefold() for p in self.files)
        added=0;skip=0
        for p in paths:
            if p.suffix.lower()!='.pdf' or is_generated_name(p.name):
                skip+=1;continue
            if str(p.resolve()).casefold() in originals:continue
            originals.add(str(p.resolve()).casefold())
            self.files.append(p);added+=1
            self.tree.insert('','end',iid=str(len(self.files)-1),values=(p.name,'-', '대기'))
        self.status.set(f'{added}개 추가 · 총 {len(self.files)}개 / 자동 처리본 제외: {skip}개')
        if self.files and not self.tree.selection():
            self.tree.selection_set(self.tree.get_children()[0]);self.selected_file()

    def remove_files(self):
        if self.busy:return
        selected=set(int(k) for k in self.tree.selection())
        self.files=[p for i,p in enumerate(self.files) if i not in selected]
        self.rebuild()

    def clear_files(self):
        if self.busy:return
        self.files=[];self.rebuild()

    def rebuild(self):
        for k in self.tree.get_children():self.tree.delete(k)
        for i,p in enumerate(self.files):self.tree.insert('','end',iid=str(i),values=(p.name,'-','대기'))
        self.preview_source=None;self.canvas.delete('all');self.page_text.config(text='0 / 0쪽')
        if self.files:self.tree.selection_set('0');self.selected_file()

    def selected_file(self,_event=None):
        if self.busy:return
        keys=self.tree.selection()
        if not keys:return
        index=int(keys[0]);path=self.files[index]
        if path!=self.preview_source:
            self.preview_source=path;self.preview_index=0
        self.preview()

    def page_change(self,change):
        if not self.preview_source or self.busy:return
        try:
            with fitz.open(str(self.preview_source)) as doc:
                self.preview_index=min(max(0,self.preview_index+change),len(doc)-1)
            self.preview()
        except Exception as e:self.preview_status.set(str(e))

    def resize(self,_event=None):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id=self.root.after(190,self.preview)

    def preview(self):
        self.after_id=None
        if not self.preview_source or self.busy:return
        path=self.preview_source
        try:
            cw=max(500,self.canvas.winfo_width()-25)
            with fitz.open(str(path)) as doc:
                index=min(self.preview_index,len(doc)-1)
                pw=doc[index].rect.width
                scale=min(1.5,max(.65,cw/pw))
                self.page_text.config(text=f'{index+1} / {len(doc)}쪽')
                if self.show_redacted.get():
                    data=preview_page(path,index,self.options(),scale)
                else:
                    data=doc[index].get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png')
            self.photo=tk.PhotoImage(data=base64.b64encode(data))
            self.canvas.delete('all')
            self.canvas.create_image(max(8,(self.canvas.winfo_width()-self.photo.width())//2),8,
                                     anchor='nw',image=self.photo)
            self.canvas.configure(scrollregion=(0,0,max(self.canvas.winfo_width(),self.photo.width()+20),self.photo.height()+18))
            self.preview_status.set(path.name+'  ·  '+('개인정보 삭제 후 미리보기' if self.show_redacted.get() else '개인정보 포함 원본(화면 공유 주의)'))
            for idx,p in enumerate(self.files):
                if p==path:
                    if self.tree.exists(str(idx)):
                        self.tree.set(str(idx),'pages',str(self.page_text.cget('text').split('/')[1].strip().split('쪽')[0]))
                        if self.tree.set(str(idx),'state') not in ('완료','실패'):
                            self.tree.set(str(idx),'state','미리보기 OK')
                    break
        except Exception as exc:
            self.canvas.delete('all')
            self.page_text.config(text='확인 필요')
            self.preview_status.set(f'자동 판독 실패: {exc}')
            for idx,p in enumerate(self.files):
                if p==path and self.tree.exists(str(idx)):
                    self.tree.set(str(idx),'state','점검 필요');break

    def choose_output(self):
        if self.busy:return
        p=filedialog.askdirectory(title='결과를 저장할 폴더 선택')
        if p:
            self.target_dir=Path(p)
            self.folder_label.set('결과 저장 폴더: '+str(self.target_dir))

    def save_batch(self):
        if self.busy:return
        if not self.files:
            messagebox.showwarning('PDF 없음','먼저 PDF 파일을 하나 이상 추가하세요.');return
        # By default output beside the first source, never overwrite originals.
        dest_dir=self.target_dir or self.files[0].parent/'면접용_결과'
        # Avoid identical output names (even if sources reside in separate folders).
        out_names=[destination_for(p,dest_dir).name.casefold() for p in self.files]
        if len(set(out_names))!=len(out_names):
            messagebox.showerror('파일명 중복','같은 이름을 가진 PDF가 목록에 두 개 이상 있습니다.\n서로 다른 이름으로 바꾼 후 진행해 주세요.')
            return
        existing=[destination_for(p,dest_dir).name for p in self.files if destination_for(p,dest_dir).exists()]
        warning=f'총 {len(self.files)}개 PDF를 자동 익명화합니다.\n\n저장 폴더: {dest_dir}\n출력 파일명: 원본파일명{SUFFIX}.pdf\n\n원본은 변경되지 않습니다.'
        if existing:
            warning += f'\n\n이미 결과가 있는 {len(existing)}개 파일은 덮어쓰지 않고 실패로 표시합니다.'
        if not messagebox.askyesno('일괄 자동 처리 확인',warning):return
        self.busy=True;self.progress.configure(maximum=len(self.files),value=0)
        self.status.set('일괄 삭제 진행 중...')
        batch=list(self.files);opts=self.options()
        threading.Thread(target=self.worker,args=(batch,dest_dir,opts),daemon=True).start()

    def worker(self,files,dest_dir,opts):
        results=[]
        for i,p in enumerate(files):
            dst=destination_for(p,dest_dir)
            try:
                result=anonymize_pdf(p,dst,opts)
                results.append((i,'완료',f'{result.pages}쪽 · {dst.name}'))
            except Exception as exc:
                results.append((i,'실패',str(exc)))
            self.events.put(('step',i,results[-1][1],results[-1][2],i+1,len(files)))
        self.events.put(('done',results,str(dest_dir)))

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='step':
                    _,i,state,detail,k,total=event
                    if self.tree.exists(str(i)):self.tree.set(str(i),'state',state)
                    self.progress['value']=k
                    self.status.set(f'{k}/{total} 처리 · {self.files[i].name}: {state}')
                elif event[0]=='done':
                    self.busy=False
                    rows=event[1];target=event[2]
                    good=sum(state=='완료' for _,state,_ in rows)
                    failed=[(self.files[i].name,detail) for i,state,detail in rows if state!='완료']
                    self.status.set(f'완료 {good}개 / 실패 {len(failed)}개 · 원본 유지')
                    msg=f'완료: {good}개\n실패: {len(failed)}개\n\n저장 폴더: {target}'
                    if failed:msg+='\n\n오류 내용(최대 5개):\n'+'\n'.join(f'{a}: {b}' for a,b in failed[:5])
                    msg+='\n\n모의면접 전에 각 PDF 첫 쪽과 모든 쪽 하단을 꼭 확인하세요.'
                    messagebox.showinfo('작업 결과',msg)
        except queue.Empty:
            pass
        self.root.after(120,self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('처리 중','일괄 작업이 완료된 뒤 종료할 수 있습니다.');return
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();SchoolRedactor(root);root.mainloop()
