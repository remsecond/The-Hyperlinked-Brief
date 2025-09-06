Write-Host "Dev header:"
python .\Scripts\orchestrator.py --branch dev --prompt Prompts/Prompt_I.md

Write-Host "`nProd header:"
python .\Scripts\orchestrator.py --branch prod --prompt Prompts/Prompt_I.md