# Política de Segurança e Privacidade — Translate_BooK

## Visão Geral e Princípios Fundamentais

O **Translate_BooK** foi projetado com a filosofia **Local-First, Privacy-by-Design e Zero-Trust**:
1. **100% Processamento Local**: Todo o pipeline de ingestão, análise de contexto, memória de entidades, OCR, inferência neural de tradução e exportação roda inteiramente na máquina do usuário.
2. **Zero Telemetria**: Não há telemetria, rastreadores, analytics, envio de metadados, identificadores ou conexões ocultas com quaisquer servidores.
3. **Privacidade Absoluta de Conteúdo**: Nenhum trecho de texto, título de livro, nome de autor, parágrafo ou documento é transmitido para nuvem ou terceiros.
4. **Isolamento de Dados**: Os projetos do usuário são armazenados localmente em bancos SQLite em modo WAL com sanitização de logs e integridade criptográfica SHA-256.

---

## Versões Suportadas

Apenas as versões mais recentes recebem atualizações de segurança e correções ativas.

| Versão | Suporte a Segurança |
|:-------|:-------------------:|
| 1.0.x  | :white_check_mark:  |
| < 1.0  | :x:                 |

---

## Arquitetura de Defesa e Hardening Implementada

### 1. Prevenção de Path Traversal (`path_guard.py`)
- Validação estrita de todos os caminhos de entrada e saída.
- Proibição de sequências como `../`, `..\\`, drives absolutos não autorizados e caracteres nulos (`\0`).
- Sanitização de identificadores de projeto e nomes de arquivo via `sanitize_filename_strict` e `validate_safe_path`.

### 2. Proteção contra Zip Slip e Zip Bombs (`zip_guard.py`)
- Em arquivos comprimidos (EPUB, DOCX):
  - **Zip Slip**: Bloqueio de entradas com caminhos relativos maliciosos (`..`) ou caminhos absolutos.
  - **Zip Bombs**: Verificação preventiva do tamanho descompactado total (limite padrão: 500 MB), tamanho individual por entrada (limite: 100 MB), razão máxima de compressão (100:1) e contagem máxima de entradas (10.000).

### 3. Prevenção de XXE e Billion Laughs (`xml_guard.py`)
- Parsers de XML e XHTML (EPUB/DOCX) operam com políticas restritivas:
  - Rejeição de `<!DOCTYPE>` contendo DTDs externos (`SYSTEM` ou `PUBLIC`).
  - Bloqueio de entidades customizadas `<!ENTITY>` para mitigar ataques de expansão quadrática/exponencial (Billion Laughs / XML Bomb).
  - Sanitização de conteúdos HTML exportados contra injeção de `<script>` e esquemas inseguros (`javascript:`, `data:`).

### 4. Gestão Segura de Subprocessos
- Todas as invocações de ferramentas externas (como Tesseract OCR) utilizam lista de argumentos (`shell=False`), eliminando riscos de Shell Injection.
- Caminhos para executáveis externos passam por resolução canônica e verificação de integridade antes da execução.

### 5. Sanitização de Logs e Redação de Dados Sensíveis (`audit.py`)
- O `PrivacySanitizingFilter` atua em todas as saídas de log:
  - Redação automática de diretórios de usuário (`C:\Users\<username>`, `/home/<username>`).
  - Redação de tokens, chaves de API potenciais e strings suspeitas.
  - Logs não expõem o conteúdo dos livros traduzidos em nível `INFO`/`WARNING`.

### 6. Integridade de Modelos e Supply Chain (`model_manager.py` e `resource_guard.py`)
- O aplicativo **nunca** embute pesos de IA no instalador ou repositório Git.
- Todos os downloads de pesos neurais utilizam estritamente o protocolo `https://`.
- Cada arquivo baixado tem seu hash SHA-256 verificado contra o catálogo oficial registrado antes de qualquer carregamento.
- Arquivos parciais (`.part`) corrompidos são descartados e nunca executados.

---

## Reportando uma Vulnerabilidade

Agradecemos a colaboração da comunidade de segurança para manter o Translate_BooK seguro.

Se você identificar uma vulnerabilidade de segurança, siga as diretrizes abaixo:

1. **NÃO** abra issues públicas no GitHub para reportar vulnerabilidades críticas de segurança.
2. Envie um e-mail confidencial para: **security@translatebook.local** (ou contate o mantenedor responsável via canal privado no repositório).
3. Inclua no relatório:
   - Descrição detalhada da vulnerabilidade;
   - Prova de conceito (PoC) ou passos reprodutíveis;
   - Impacto estimado (e.g. DoS local, vazamento de arquivo, etc.);
   - Ambiente de teste (versão do Translate_BooK, versão do Windows/Linux).

### Prazos e Compromisso de Resposta
- **Confirmação inicial de recebimento**: até 48 horas úteis.
- **Avaliação de impacto e triagem**: até 5 dias úteis.
- **Correção e publicação de patch**: prazo médio de 14 a 30 dias dependendo da criticidade, com divulgação coordenada e agradecimento nos créditos (se desejado pelo pesquisador).
