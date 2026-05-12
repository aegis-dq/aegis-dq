Output docs/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Catppuccin Mocha"
Set Padding 20
Set PlaybackSpeed 1.5

Type "python3 demo/seed_demo.py" Sleep 500ms Enter
Sleep 3s

Type "aegis validate demo/rules.yaml" Sleep 500ms Enter
Sleep 2s

Type "aegis run demo/rules.yaml --db /tmp/aegis_demo.db --no-llm" Sleep 500ms Enter
Sleep 4s

Sleep 3s
