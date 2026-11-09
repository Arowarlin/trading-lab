from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "tradinglab" / "webui" / "index.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node no disponible")

SCRIPT = r"""
const fs = require("fs");
const text = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");

function extractFunction(name) {
  const start = text.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing function ${name}`);
  const open = text.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  throw new Error(`unclosed function ${name}`);
}

function extractConst(name) {
  const start = text.indexOf(`const ${name} =`);
  if (start < 0) throw new Error(`missing const ${name}`);
  const end = text.indexOf(";", start);
  return text.slice(start, end + 1);
}

const code = [
  extractConst("fmtUSD"),
  extractFunction("clampZero"),
  extractFunction("money"),
  extractFunction("num"),
  extractFunction("pct"),
  extractFunction("pctRaw"),
  extractFunction("toneFor"),
  extractFunction("esc"),
  extractFunction("gaugeArcPoint"),
  extractFunction("gaugeCardHtml"),
  extractFunction("cushionTone"),
  extractFunction("cushionStatus"),
  extractConst("ASSET_ALIASES"),
  extractFunction("assetGroup"),
  extractFunction("sameAsset"),
].join("\n");

const test = `
const zeroPct = pct(-0.00004, 2);
const zeroPctRaw = pctRaw(-0.00004, 2);
const zeroTone = toneFor(-0.00004, 2);
const positiveTone = toneFor(0.0123, 2);
const negativeTone = toneFor(-0.0123, 2);
const groupedMoney = money(9973.51);
const zeroMoney = money(-0.001);
const gaugeEmpty = gaugeCardHtml({key:"daily", label:"Colchón diario", available:true, used:0, value:"100%", note:"", tone:"ok", status:"HOLGADO", aria:"x"});
const gaugeLimit = gaugeCardHtml({key:"daily", label:"Colchón diario", available:true, used:0.8, value:"20%", note:"", tone:"bad", status:cushionStatus(0.8), aria:"x"});
const aliasUS = sameAsset("US100.cash", "NASDAQ");
const aliasGold = sameAsset("GOLD", "XAUUSD");
const aliasNo = sameAsset("SPY", "QQQ");
console.log(JSON.stringify({zeroPct, zeroPctRaw, zeroTone, positiveTone, negativeTone, groupedMoney, zeroMoney, gaugeEmpty, gaugeLimit, status08: cushionStatus(0.8), tone08: cushionTone(0.8), aliasUS, aliasGold, aliasNo}));
`;

new Function(code + test)();
"""


def _run_js() -> dict:
    proc = subprocess.run(
        [NODE, "-e", SCRIPT, "--", str(INDEX)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_formateador_cero_negativo_y_miles() -> None:
    result = _run_js()
    assert result["zeroPct"] == "0.00%"
    assert result["zeroPctRaw"] == "0.00%"
    assert result["zeroTone"] == "flat"
    assert result["positiveTone"] == "pos"
    assert result["negativeTone"] == "neg"
    assert "9.973,51" in result["groupedMoney"]
    assert not result["zeroMoney"].strip().startswith("-")


def test_gauge_dibuja_lo_que_queda() -> None:
    result = _run_js()
    assert 'stroke-dasharray="100.0 100"' in result["gaugeEmpty"]
    assert 'stroke-dasharray="20.0 100"' in result["gaugeLimit"]
    assert "AL LÍMITE" in result["gaugeLimit"]
    assert result["status08"] == "AL LÍMITE"
    assert result["tone08"] == "bad"


def test_alias_de_activo_en_la_vista_por_activo() -> None:
    result = _run_js()
    assert result["aliasUS"] is True
    assert result["aliasGold"] is True
    assert result["aliasNo"] is False
