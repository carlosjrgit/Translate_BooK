# Guia de Contribuição — Translate_BooK

Agradecemos o seu interesse em contribuir para o **Translate_BooK**! Este projeto é construído em torno de uma filosofia rigorosa de engenharia:
> **"Modelo competente + Contexto correto + Memória persistente + Regras + Validação + Auditoria."**

---

## 1. Princípios Inegociáveis do Projeto

Ao propor melhorias ou submeter código, respeite sempre estes pilares:
1. **100% Local e Offline**: Todo processamento editorial deve ocorrer no dispositivo do usuário. Nenhuma requisição a servidores de terceiros ou serviços de nuvem externos é permitida para tradução.
2. **Zero Telemetria**: É terminantemente proibido adicionar rastreadores, telemetria, contadores de uso ou qualquer coleta de dados.
3. **Nenhum Peso Neural no Git**: O repositório Git contém exclusivamente código-fonte, schemas SQL e documentação. Pesos de IA (como arquivos `.bin`, `.safetensors`, `.gguf`) são gerenciados pelo `ModelManager` via download seguro sob demanda.
4. **Respeito ao Original**: A integridade estrutural da obra original e os projetos do usuário em `%APPDATA%/Translate_BooK/projects` nunca devem ser sobrescritos ou excluídos em atualizações ou desinstalações.

---

## 2. Configuração do Ambiente de Desenvolvimento

### Requisitos Prévios
- **Python**: Versão 3.10 ou superior (testado em 3.10, 3.11, 3.12, 3.13 e 3.14).
- **Git** instalado.
- **Tesseract OCR** (opcional, necessário apenas para módulo de OCR escaneado).

### Passos de Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/Translate_BooK.git
cd Translate_BooK

# 2. Crie e ative um ambiente virtual
python -m venv .venv

# No Windows (PowerShell):
.venv\Scripts\Activate.ps1
# No Linux/macOS:
source .venv/bin/activate

# 3. Instale em modo editável com dependências
pip install -e .
pip install pytest ruff pyinstaller
```

---

## 3. Estrutura do Código-Fonte

```
src/book_translator/
├── analysis/         # Análise estrutural global, NER heurístico e resolução de entidades
├── consistency/      # Consistency Pass intercapítulos (lemas, pronomes, terminologia)
├── context/          # Mecanismo de resolução de contexto pré-tradução
├── database/         # SQLite (modo WAL), migrations SQL incrementais e schemas
├── export/           # Exportadores determinísticos (TXT, DOCX, EPUB)
├── memory/           # Style Bible, Memória de História, Entidades e Termos travados
├── ocr/              # Módulo isolado de OCR para PDFs escaneados (Tesseract)
├── parsers/          # Parsers seguros (TXT, DOCX, EPUB, PDF textual)
├── preprocessing/    # Segmentação inteligente por sentenças e preservação de tags
├── qa/               # QA Determinístico (números, pontuação, tags) e Semântico
├── security/         # Guards de Path Traversal, Zip Slip/Bomb, XXE e Sanitização de Logs
├── system/           # Detecção de hardware (GPU/VRAM/RAM) e gerenciador de modelos
├── translation/      # Motor de inferência CTranslate2 (MADLAD-400), N-best e Cache
└── ui/               # Interface gráfica moderna em PySide6 (Qt)
```

---

## 4. Padrões de Código e Qualidade

- **Tipagem Estática**: Utilize type hints do Python em todas as assinaturas de funções e classes (`def foo(param: str) -> bool:`).
- **Linter & Formatador**: Utilizamos `ruff` para análise estática e linting:
  ```bash
  python -m ruff check src tests
  ```
- **Docstrings**: Todas as classes e métodos públicos devem conter docstrings explicativas em português ou inglês.
- **Segurança de Subprocessos**: Invocação de processos externos deve sempre usar `subprocess.run(["cmd", "arg"], shell=False)`.
- **Manipulação de Arquivos e Zip**: Sempre utilize os métodos em `book_translator.security` (`validate_safe_path`, `validate_zip_archive`, etc.).

---

## 5. Execução dos Testes

Antes de submeter qualquer Pull Request, certifique-se de que a suíte de testes completa passa sem erros:

```bash
# Executar toda a suíte de testes (319+ testes)
python -m pytest

# Executar testes com relatório detalhado
python -m pytest -v

# Executar testes de segurança específicos
python -m pytest tests/security/ -v

# Executar testes de integração end-to-end
python -m pytest tests/integration/ -v
```

---

## 6. Fluxo de Submissão de Pull Request (PR)

1. Crie uma branch específica para sua funcionalidade ou correção:
   ```bash
   git checkout -b feature/minha-melhoria
   # ou
   git checkout -b fix/correcao-bug
   ```
2. Adicione testes unitários cobrindo o novo comportamento em `tests/unit/`, `tests/security/` ou `tests/integration/`.
3. Garanta que o linter e os testes passem 100%.
4. Escreva commits claros e atômicos:
   - `feat(export): adiciona suporte a notas de rodapé personalizadas em EPUB`
   - `fix(security): valida tamanho máximo de descompressão em DOCX`
5. Abra o Pull Request descrevendo claramente a motivação da mudança, os testes executados e referências a eventuais issues.

Agradecemos por ajudar a tornar a tradução de livros cada vez mais acessível, privada e de alta qualidade editorial!
