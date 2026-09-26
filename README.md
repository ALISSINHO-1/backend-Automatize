# Automatize - Backend

Backend da plataforma **Automatize**, projeto desenvolvido para a disciplina de Programação Orientada a Objetos em Python do 4º período de Engenharia de Software.

O backend é responsável pelas regras de negócio, automações, autenticação, controle do ciclo de vida das solicitações, comunicação com o banco de dados e disponibilização dos serviços utilizados pelas aplicações Web e Mobile.

---

## Sobre o projeto

O Automatize foi desenvolvido com o objetivo de centralizar e automatizar processos operacionais de pequenos empreendedores e organizações.

No cenário analisado, solicitações, ajustes, informações e aprovações são frequentemente registrados por meios descentralizados, como mensagens, e-mails e anotações.

A aplicação busca centralizar essas informações e fornecer rastreabilidade durante todo o ciclo de atendimento.

---

## Principais funcionalidades

O backend é responsável por:

- autenticação e autorização de usuários;
- cadastro e gerenciamento de solicitações;
- gerenciamento de tarefas;
- controle do ciclo de vida dos atendimentos;
- automação de mudanças de estado;
- cálculo de progresso;
- registro de ocorrências;
- armazenamento de histórico;
- aprovação e homologação de entregas;
- registro de data, hora e responsável pela aprovação;
- gerenciamento de anexos e evidências;
- integração com PostgreSQL/Supabase;
- disponibilização de API REST;
- documentação automática utilizando Swagger/OpenAPI.

---

## Fluxo principal

O ciclo de vida previsto para uma solicitação é:

```text
Planejamento
     ↓
Execução
     ↓
Homologação
     ↓
Concluído
