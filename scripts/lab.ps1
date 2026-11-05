param([Parameter(ValueFromRemainingArguments = $true)] $Args)
$env:PYTHONUTF8 = "1"
& "E:\trading-lab\.venv\Scripts\lab.exe" @Args
