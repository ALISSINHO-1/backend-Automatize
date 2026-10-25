import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.enums import StatusDemandaEnum
from app.services.demand_service import DemandService
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    AprovacaoNaoAutorizadaException
)


class NovaDemandaDialog(tk.Toplevel):

    def __init__(self, parent, on_sucesso_callback, demanda=None):
        super().__init__(parent)
        self.demanda = demanda
        self.title("Editar Demanda" if demanda else "Cadastrar Nova Demanda")
        self.geometry("420x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_sucesso_callback = on_sucesso_callback

        self._construir_formulario()
        if demanda:
            self._preencher_formulario()

    def _preencher_formulario(self):
        self.entry_titulo.insert(0, self.demanda.titulo)
        self.entry_cliente.insert(0, self.demanda.cliente_id)
        self.entry_cliente.configure(state="disabled")
        self.text_descricao.insert("1.0", self.demanda.descricao)

    def _construir_formulario(self):
        pad_opts = {"padx": 15, "pady": 6}

        ttk.Label(self, text="Título da Demanda:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.entry_titulo = ttk.Entry(self, width=45)
        self.entry_titulo.pack(fill="x", padx=15)

        ttk.Label(self, text="Identificador do Cliente:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.entry_cliente = ttk.Entry(self, width=45)
        self.entry_cliente.pack(fill="x", padx=15)

        ttk.Label(self, text="Descrição Detalhada:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.text_descricao = tk.Text(self, width=45, height=5, font=("Segoe UI", 9))
        self.text_descricao.pack(fill="x", padx=15)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=15, padx=15)

        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Salvar Demanda", command=self._submeter).pack(side="right")

    def _submeter(self):
        titulo = self.entry_titulo.get()
        cliente = self.entry_cliente.get()
        descricao = self.text_descricao.get("1.0", "end-1c")

        try:
            if self.demanda:
                DemandService.update(self.demanda.id, titulo=titulo, descricao=descricao)
                messagebox.showinfo("Sucesso", "Demanda atualizada com sucesso!")
            else:
                DemandService.create(titulo=titulo, descricao=descricao, cliente_id=cliente)
                messagebox.showinfo("Sucesso", "Demanda cadastrada com sucesso!")
            self.on_sucesso_callback()
            self.destroy()
        except RegraNegocioException as erro:
            messagebox.showerror("Erro de Validação", str(erro))


class AutomatizeDesktopApp(tk.Tk):

    INTERVALO_AUTO_REFRESH_MS = 5000

    def __init__(self):
        super().__init__()
        self.title("Automatize - Gestão Operacional de Demandas")
        self.geometry("960x540")
        self.minsize(800, 450)

        self._inicializar_dados_mock()
        self._construir_interface()
        self.carregar_demandas()
        self._agendar_auto_refresh()

    def _inicializar_dados_mock(self):
        if not DemandService.list_all():
            d1 = DemandService.create("Manutenção Notebook Dell", "Troca de pasta térmica e teclado", "cliente_valente")
            d2 = DemandService.create("Configuração Rede Local", "Roteamento de switches e firewall", "empresa_parceira")
            DemandService.change_status(d2.id, StatusDemandaEnum.EXECUCAO)

    def _construir_interface(self):
        top_bar = ttk.Frame(self, padding=12)
        top_bar.pack(fill="x")

        ttk.Label(
            top_bar,
            text="Painel de Controlo de Demandas",
            font=("Segoe UI", 14, "bold")
        ).pack(side="left")

        ttk.Button(
            top_bar,
            text="+ Nova Demanda",
            command=self._abrir_modal_cadastro
        ).pack(side="right", padx=5)

        ttk.Button(
            top_bar,
            text="Recarregar",
            command=self.carregar_demandas
        ).pack(side="right")
        grid_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        grid_frame.pack(fill="both", expand=True)

        colunas = ("id", "titulo", "cliente", "status", "progresso", "criado_em")
        self.tree = ttk.Treeview(grid_frame, columns=colunas, show="headings", selectmode="browse")

        self.tree.heading("id", text="ID")
        self.tree.heading("titulo", text="Título")
        self.tree.heading("cliente", text="Cliente")
        self.tree.heading("status", text="Estado")
        self.tree.heading("progresso", text="Progresso")
        self.tree.heading("criado_em", text="Data de Criação")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("titulo", width=250, anchor="w")
        self.tree.column("cliente", width=140, anchor="w")
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("progresso", width=100, anchor="center")
        self.tree.column("criado_em", width=150, anchor="center")

        scrollbar = ttk.Scrollbar(grid_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # SCRUM-20: Barra Inferior com Acoes de Edicao de Estado e Exclusao
        bottom_bar = ttk.Frame(self, padding=12)
        bottom_bar.pack(fill="x")

        ttk.Button(
            bottom_bar,
            text="Avançar Estado",
            command=self._acao_avancar_estado
        ).pack(side="left", padx=4)

        ttk.Button(
            bottom_bar,
            text="Aprovar Homologação",
            command=self._acao_aprovar_homologacao
        ).pack(side="left", padx=4)

        ttk.Button(
            bottom_bar,
            text="Rejeitar Homologação",
            command=self._acao_rejeitar_homologacao
        ).pack(side="left", padx=4)

        ttk.Button(
            bottom_bar,
            text="Excluir Demanda",
            command=self._acao_excluir_demanda
        ).pack(side="right", padx=4)

        ttk.Button(
            bottom_bar,
            text="Editar Demanda",
            command=self._acao_editar_demanda
        ).pack(side="right", padx=4)

    def _obter_id_selecionado(self):
        selecionado = self.tree.selection()
        if not selecionado:
            messagebox.showwarning("Atenção", "Selecione uma demanda na tabela primeiro.")
            return None
        valores = self.tree.item(selecionado[0], "values")
        return int(valores[0])

    def carregar_demandas(self):
        selecionado_anterior = self._obter_id_selecionado_sem_aviso()

        for item in self.tree.get_children():
            self.tree.delete(item)

        demandas = DemandService.list_all()
        for d in demandas:
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    d.id,
                    d.titulo,
                    d.cliente_id,
                    d.status.value,
                    f"{d.percentual_progresso:.0f}%",
                    d.criado_em.strftime("%d/%m/%Y %H:%M")
                )
            )
            if selecionado_anterior == d.id:
                self.tree.selection_set(item_id)

    def _obter_id_selecionado_sem_aviso(self):
        selecionado = self.tree.selection()
        if not selecionado:
            return None
        return int(self.tree.item(selecionado[0], "values")[0])

    def _agendar_auto_refresh(self):
        self.carregar_demandas()
        self.after(self.INTERVALO_AUTO_REFRESH_MS, self._agendar_auto_refresh)

    def _abrir_modal_cadastro(self):
        NovaDemandaDialog(self, on_sucesso_callback=self.carregar_demandas)

    def _acao_editar_demanda(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        demanda = DemandService.get_by_id(demanda_id)
        if demanda.status == StatusDemandaEnum.CONCLUIDO:
            messagebox.showinfo("Informação", "Demandas concluídas possuem aceite formal e não podem ser editadas.")
            return

        NovaDemandaDialog(self, on_sucesso_callback=self.carregar_demandas, demanda=demanda)

    def _acao_avancar_estado(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        demanda = DemandService.get_by_id(demanda_id)
        proximos = DemandService.TRANSICOES_VALIDAS.get(demanda.status, [])

        if not proximos:
            messagebox.showinfo("Informação", "Esta demanda já se encontra em estado final imutável.")
            return

        novo_status = proximos[0]
        try:
            DemandService.change_status(demanda_id, novo_status)
            self.carregar_demandas()
            messagebox.showinfo("Sucesso", f"Demanda #{demanda_id} transitou para {novo_status.value}!")
        except RegraNegocioException as erro:
            messagebox.showerror("Bloqueio de Regra", str(erro))

    def _acao_aprovar_homologacao(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        demanda = DemandService.get_by_id(demanda_id)
        try:
            DemandService.aprovar_homologacao(demanda_id, cliente_id=demanda.cliente_id)
            self.carregar_demandas()
            messagebox.showinfo("Homologado", f"Demanda #{demanda_id} homologada e concluída com 100% de progresso!")
        except (AprovacaoNaoAutorizadaException, RegraNegocioException) as erro:
            messagebox.showerror("Erro na Homologação", str(erro))

    def _acao_rejeitar_homologacao(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        motivo = tk.simpledialog.askstring(
            "Rejeitar Homologação",
            "Informe o motivo da rejeição (mínimo 10 caracteres):",
            parent=self
        )

        if motivo is None:
            return

        try:
            DemandService.rejeitar_homologacao(demanda_id, motivo_rejeicao=motivo)
            self.carregar_demandas()
            messagebox.showwarning("Retorno", f"Demanda #{demanda_id} retornou para EXECUCAO para correção.")
        except (TransicaoEstadoInvalidaException, RegraNegocioException) as erro:
            messagebox.showerror("Erro de Validação", str(erro))

    def _acao_excluir_demanda(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        confirmar = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Deseja realmente excluir a demanda #{demanda_id}?"
        )
        if confirmar:
            try:
                DemandService.delete(demanda_id)
                self.carregar_demandas()
                messagebox.showinfo("Excluída", f"Demanda #{demanda_id} removida com sucesso.")
            except RegraNegocioException as erro:
                messagebox.showerror("Bloqueio de Regra", str(erro))


if __name__ == "__main__":
    import tkinter.simpledialog
    app = AutomatizeDesktopApp()
    app.mainloop()