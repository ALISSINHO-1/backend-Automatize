import sys
import os
import tkinter as tk
import tkinter.simpledialog
from tkinter import ttk, messagebox
from uuid import UUID

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.core.exceptions import RegraNegocioException
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, AuthenticationError
from app.services.demand_service import DemandService


# Avanco manual permitido ao tecnico/ADMIN; a saida de HOMOLOGACAO e do cliente.
PROXIMO_ESTADO = {
    StatusPedidoEnum.PLANEAMENTO: StatusPedidoEnum.EXECUCAO,
    StatusPedidoEnum.EXECUCAO: StatusPedidoEnum.HOMOLOGACAO,
}


class LoginDialog(tk.Toplevel):
    """Autentica com as mesmas credenciais da API; o usuario vira o autor das acoes."""

    def __init__(self, parent, session_factory, settings):
        super().__init__(parent)
        self.title("Automatize - Entrar")
        self.geometry("360x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.session_factory = session_factory
        self.settings = settings
        self.usuario = None

        pad_opts = {"padx": 15, "pady": 4}
        ttk.Label(self, text="E-mail:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.entry_email = ttk.Entry(self, width=40)
        self.entry_email.pack(fill="x", padx=15)
        ttk.Label(self, text="Senha:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.entry_senha = ttk.Entry(self, width=40, show="*")
        self.entry_senha.pack(fill="x", padx=15)
        self.entry_senha.bind("<Return>", lambda _evento: self._entrar())

        ttk.Button(self, text="Entrar", command=self._entrar).pack(pady=15)
        self.entry_email.focus_set()

    def _entrar(self):
        email = self.entry_email.get().strip()
        try:
            with self.session_factory() as db:
                AuthService(db, self.settings).authenticate(email, self.entry_senha.get())
                usuario = UserRepository(db).get_by_email(email)
                db.expunge(usuario)
        except AuthenticationError:
            messagebox.showerror("Acesso negado", "E-mail ou senha inválidos.", parent=self)
            return
        except SQLAlchemyError:
            messagebox.showerror("Erro de conexão", "Não foi possível acessar o banco de dados.", parent=self)
            return

        self.usuario = usuario
        self.destroy()


class NovaDemandaDialog(tk.Toplevel):

    def __init__(self, parent, on_sucesso_callback, demanda=None):
        super().__init__(parent)
        self.app = parent
        self.demanda = demanda
        self.title("Editar Demanda" if demanda else "Cadastrar Nova Demanda")
        self.geometry("420x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_sucesso_callback = on_sucesso_callback
        # So o ADMIN escolhe o cliente; para o CLIENTE a demanda e sempre dele.
        self.informa_cliente = demanda is None and parent.usuario.perfil == PerfilEnum.ADMIN

        self._construir_formulario()
        if demanda:
            self._preencher_formulario()

    def _preencher_formulario(self):
        self.entry_titulo.insert(0, self.demanda.titulo)
        self.text_descricao.insert("1.0", self.demanda.descricao or "")

    def _construir_formulario(self):
        pad_opts = {"padx": 15, "pady": 6}

        ttk.Label(self, text="Título da Demanda:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
        self.entry_titulo = ttk.Entry(self, width=45)
        self.entry_titulo.pack(fill="x", padx=15)

        if self.informa_cliente:
            ttk.Label(self, text="E-mail do Cliente:", font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad_opts)
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
        descricao = self.text_descricao.get("1.0", "end-1c")

        def salvar(service, db):
            if self.demanda:
                service.editar(self.app.usuario, self.demanda.id, titulo=titulo, descricao=descricao)
                return "Demanda atualizada com sucesso!"
            cliente_id = None
            if self.informa_cliente:
                cliente = UserRepository(db).get_by_email(self.entry_cliente.get().strip())
                if cliente is None:
                    raise RegraNegocioException("Nenhum usuário encontrado com este e-mail.")
                cliente_id = cliente.id
            service.criar(self.app.usuario, titulo=titulo, descricao=descricao, cliente_id=cliente_id)
            return "Demanda cadastrada com sucesso!"

        mensagem = self.app.executar(salvar, titulo_erro="Erro de Validação", parent=self)
        if mensagem:
            messagebox.showinfo("Sucesso", mensagem, parent=self)
            self.on_sucesso_callback()
            self.destroy()


class AutomatizeDesktopApp(tk.Tk):

    INTERVALO_AUTO_REFRESH_MS = 5000

    def __init__(self):
        super().__init__()
        self.title("Automatize - Gestão Operacional de Demandas")
        self.geometry("960x540")
        self.minsize(800, 450)
        self.withdraw()

        self.settings = Settings()
        self.settings.validate_application_configuration()
        self.session_factory = create_session_factory(create_database_engine(self.settings))
        self.usuario = self._autenticar()
        if self.usuario is None:
            self.destroy()
            return

        self.deiconify()
        self._construir_interface()
        self.carregar_demandas()
        self._agendar_auto_refresh()

    def _autenticar(self):
        login = LoginDialog(self, self.session_factory, self.settings)
        self.wait_window(login)
        return login.usuario

    def executar(self, operacao, *, titulo_erro="Bloqueio de Regra", parent=None):
        """Roda a operacao numa sessao propria e exibe violacoes de regra."""
        try:
            with self.session_factory() as db:
                return operacao(DemandService(db), db)
        except RegraNegocioException as erro:
            messagebox.showerror(titulo_erro, str(erro), parent=parent or self)
        except SQLAlchemyError:
            messagebox.showerror("Erro de banco", "Não foi possível concluir a operação no banco.", parent=parent or self)
        return None

    def _construir_interface(self):
        top_bar = ttk.Frame(self, padding=12)
        top_bar.pack(fill="x")

        ttk.Label(
            top_bar,
            text="Painel de Controlo de Demandas",
            font=("Segoe UI", 14, "bold")
        ).pack(side="left")

        ttk.Label(
            top_bar,
            text=f"{self.usuario.nome} ({self.usuario.perfil.value})"
        ).pack(side="left", padx=12)

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

        colunas = ("codigo", "titulo", "status", "progresso", "criado_em")
        self.tree = ttk.Treeview(grid_frame, columns=colunas, show="headings", selectmode="browse")

        self.tree.heading("codigo", text="Código")
        self.tree.heading("titulo", text="Título")
        self.tree.heading("status", text="Estado")
        self.tree.heading("progresso", text="Progresso")
        self.tree.heading("criado_em", text="Data de Criação")

        self.tree.column("codigo", width=110, anchor="center")
        self.tree.column("titulo", width=330, anchor="w")
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
        demanda_id = self._obter_id_selecionado_sem_aviso()
        if demanda_id is None:
            messagebox.showwarning("Atenção", "Selecione uma demanda na tabela primeiro.")
        return demanda_id

    def _obter_id_selecionado_sem_aviso(self):
        selecionado = self.tree.selection()
        return UUID(selecionado[0]) if selecionado else None

    def _obter_demanda(self, demanda_id):
        return self.executar(lambda service, db: service.obter(self.usuario, demanda_id))

    def carregar_demandas(self):
        selecionado_anterior = self._obter_id_selecionado_sem_aviso()
        demandas = self.executar(lambda service, db: service.listar(self.usuario))
        if demandas is None:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        for d in demandas:
            # O iid da linha e o UUID da demanda.
            self.tree.insert(
                "",
                "end",
                iid=str(d.id),
                values=(
                    d.codigo_identificador,
                    d.titulo,
                    d.status.value,
                    f"{d.percentual_progresso or 0:.0f}%",
                    d.created_at.strftime("%d/%m/%Y %H:%M") if d.created_at else ""
                )
            )
        if selecionado_anterior and self.tree.exists(str(selecionado_anterior)):
            self.tree.selection_set(str(selecionado_anterior))

    def _agendar_auto_refresh(self):
        self.carregar_demandas()
        self.after(self.INTERVALO_AUTO_REFRESH_MS, self._agendar_auto_refresh)

    def _abrir_modal_cadastro(self):
        NovaDemandaDialog(self, on_sucesso_callback=self.carregar_demandas)

    def _acao_editar_demanda(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        demanda = self._obter_demanda(demanda_id)
        if demanda is None:
            return
        if demanda.status == StatusPedidoEnum.CONCLUIDO:
            messagebox.showinfo("Informação", "Demandas concluídas possuem aceite formal e não podem ser editadas.")
            return

        NovaDemandaDialog(self, on_sucesso_callback=self.carregar_demandas, demanda=demanda)

    def _acao_avancar_estado(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        demanda = self._obter_demanda(demanda_id)
        if demanda is None:
            return
        novo_status = PROXIMO_ESTADO.get(demanda.status)
        if novo_status is None:
            messagebox.showinfo(
                "Informação",
                "Demandas em HOMOLOGACAO aguardam o aceite ou a rejeição do cliente; "
                "demandas CONCLUIDAS são imutáveis."
            )
            return

        if self.executar(lambda service, db: service.alterar_status(self.usuario, demanda.id, novo_status)):
            self.carregar_demandas()
            messagebox.showinfo("Sucesso", f"Demanda {demanda.codigo_identificador} transitou para {novo_status.value}!")

    def _acao_aprovar_homologacao(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        versao = tk.simpledialog.askstring("Aceite Formal", "Versão do entregável aprovada:", parent=self)
        if versao is None:
            return
        declaracao = tk.simpledialog.askstring(
            "Aceite Formal",
            "Declaração de aceite (mínimo 10 caracteres):",
            parent=self
        )
        if declaracao is None:
            return

        aceite = self.executar(
            lambda service, db: service.aprovar_homologacao(
                self.usuario, demanda_id, versao_entregavel=versao, declaracao_aceite=declaracao
            ),
            titulo_erro="Erro na Homologação",
        )
        if aceite:
            self.carregar_demandas()
            messagebox.showinfo("Homologado", "Demanda homologada e concluída com 100% de progresso!")

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

        # Le o codigo dentro da sessao: apos o commit o objeto expira.
        codigo = self.executar(
            lambda service, db: service.rejeitar_homologacao(
                self.usuario, demanda_id, motivo=motivo
            ).codigo_identificador,
            titulo_erro="Erro de Validação",
        )
        if codigo:
            self.carregar_demandas()
            messagebox.showwarning("Retorno", f"Demanda {codigo} retornou para EXECUCAO para correção.")

    def _acao_excluir_demanda(self):
        demanda_id = self._obter_id_selecionado()
        if not demanda_id:
            return

        confirmar = messagebox.askyesno(
            "Confirmar Exclusão",
            "Deseja realmente excluir a demanda selecionada?"
        )
        if confirmar:
            def excluir(service, db):
                service.excluir(self.usuario, demanda_id)
                return True

            if self.executar(excluir):
                self.carregar_demandas()
                messagebox.showinfo("Excluída", "Demanda removida com sucesso.")


if __name__ == "__main__":
    app = AutomatizeDesktopApp()
    if app.usuario is not None:
        app.mainloop()
