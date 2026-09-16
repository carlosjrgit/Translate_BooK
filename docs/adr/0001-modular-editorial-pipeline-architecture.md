# ADR 0001: Arquitetura Editorial Modular e Desacoplamento do Motor de Tradução

## Status
Aprovado (Accepted)

## Contexto
A tradução de obras literárias e documentos extensos de inglês para português brasileiro exige mais do que submeter blocos de texto a um modelo linguístico. Falhas comuns em abordagens simplistas incluem:
- Perda de continuidade de nomes, pronomes e formas de tratamento ao longo de dezenas de capítulos;
- Alucinações de datas, números e medidas;
- Omissões silenciosas de cláusulas e orações;
- Dependência de provedores proprietários em nuvem (comprometendo privacidade e custos).

## Decisão
1. **Separação Rígida de Responsabilidades**:
   - **Motor de Tradução**: Focado estritamente na tradução de máquina (inicialmente o modelo especializado MADLAD-400-10B-MT). Não será tratado como um chat generativo nem sobrecarregado com regras conversacionais.
   - **Cérebro Editorial**: Sistema modular em Python encarregado de ingestão, análise global prévia, memórias persistentes (Character Memory, Translation Memory, Glossary, Style Bible), recuperação seletiva de contexto, controle de qualidade híbrido (QA determinístico + semântico) e auditoria de consistência global (*Consistency Pass*).
2. **Interface Abstrata de Motor**:
   - O núcleo do sistema interage com um protocolo abstrato `TranslationEngine`. O MADLAD será encapsulado via `MADLADAdapter`, viabilizando troca ou adição de outros motores sem refatorar o restante do sistema.
3. **Execução 100% Local**:
   - Todo o processamento ocorrerá na máquina do usuário, sem transmissão de texto para APIs externas de terceiros.
4. **Persistência Incremental**:
   - Cada segmento traduzido e validado é gravado imediatamente em banco persistente por projeto (`projects/<book>/project.db`), suportando pausa, retomada e recuperação a falhas.

## Consequências
- **Positivas**:
  - Elevada consistência terminológica e contextual ao longo de livros inteiros.
  - Independência total de fornecedores em nuvem e soberania dos dados do usuário.
  - Baixo acoplamento entre o modelo de tradução e a lógica de negócios da obra.
- **Compromissos**:
  - Maior complexidade arquitetural no pipeline editorial local.
  - Necessidade de gerenciar recursos de hardware (RAM/VRAM) e quantização na máquina do usuário.
