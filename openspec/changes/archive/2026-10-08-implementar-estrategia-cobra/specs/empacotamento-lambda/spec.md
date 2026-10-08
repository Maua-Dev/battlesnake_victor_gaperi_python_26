## Purpose

Garante que o código da cobra importa do mesmo jeito que a Lambda o carrega (`src/` como raiz e handler `app.main.handler`), para que um import absoluto `src.app...` seja barrado pelos testes antes do deploy.

## ADDED Requirements

### Requirement: Pacote importável com src como raiz
O pacote `app` SHALL ser importável com `src/` como diretório de trabalho, sem depender do prefixo `src.`. A suíte de testes SHALL verificar isso, de modo que uma falha bloqueie o deploy no CD.

#### Scenario: Imports relativos
- **WHEN** `import app.main` é executado num processo Python novo com `src/` como diretório de trabalho
- **THEN** o processo termina com código de saída 0

#### Scenario: Import absoluto escapou
- **WHEN** algum módulo dentro de `src/app/` importa `from src.app...`
- **THEN** o import falha com `ModuleNotFoundError` e o teste falha
