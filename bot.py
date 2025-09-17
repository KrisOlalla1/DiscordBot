import os
import json
import pathlib
import re
import discord
from discord.ext import commands

# ======================
# Configuración
# ======================
PREFIX = "!"
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.getenv("DATA_FILE",
                      "sistemas.json")  # en Replit puedes dejarlo así

intents = discord.Intents.default()
intents.message_content = True  # necesario para comandos con prefijo
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ======================
# Persistencia de datos
# ======================
pathlib.Path(DATA_FILE).parent.mkdir(parents=True, exist_ok=True)


def load_data():
    """Carga JSON; si no existe, crea estructura base."""
    if not pathlib.Path(DATA_FILE).exists():
        base = {"_meta": {"boards": {}}}
        save_data(base)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # sanea clave _meta si no existe
    if "_meta" not in data or not isinstance(data["_meta"], dict):
        data["_meta"] = {"boards": {}}
    if "boards" not in data["_meta"] or not isinstance(data["_meta"]["boards"],
                                                       dict):
        data["_meta"]["boards"] = {}
    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


sistemas = load_data()

# ======================
# Utilidades de tablero
# ======================
PAT_ACT_TIPO = re.compile(r"^(?P<base>.+?)_(?P<tipo>CORP|NUESTRA)$",
                          re.IGNORECASE)


def pretty_activity_name(act_name: str, tipo: str) -> str:
    """
    Convierte 'NDS_CORP' -> 'NDS (CORP)' si coincide el patrón.
    Si ya viene 'LUNAR' u otra, lo deja tal cual con (TIPO).
    """
    m = PAT_ACT_TIPO.match(act_name)
    if m:
        base = m.group("base").upper()
        return f"{base} ({tipo})"
    return f"{act_name} ({tipo})"


def tablero_texto() -> str:
    """
    Genera el texto del tablero con todos los sistemas y actividades.
    """
    lineas = ["**📋 Estado de Actividades**"]
    # solo sistemas (excluir _meta)
    solo_sistemas = [k for k in sistemas.keys() if k != "_meta"]
    if not solo_sistemas:
        lineas.append("_(vacío; usa `!agregar ...`)_")
        return "\n".join(lineas)

    for sistema in solo_sistemas:
        acts = sistemas.get(sistema, {})
        if not acts or not isinstance(acts, dict):
            continue
        actividades = {
            a: v
            for a, v in acts.items()
            if isinstance(v, dict) and "total" in v and "hecho" in v
        }
        if not actividades:
            continue

        lineas.append(f"**{sistema}**")
        for act, dat in actividades.items():
            tipo = str(dat.get("tipo", "N/A")).upper()
            hecho = int(dat.get("hecho", 0))
            total = int(dat.get("total", 0))
            nombre = pretty_activity_name(act, tipo)
            lineas.append(f" → {nombre}: {hecho}/{total}")

    if len(lineas) == 1:
        lineas.append("_(vacío; usa `!agregar ...`)_")
    return "\n".join(lineas)


async def actualizar_tablero(channel: discord.TextChannel):
    """
    Mantiene un único mensaje de tablero por canal:
    - Si existe, lo edita.
    - Si no, crea uno nuevo y guarda su ID en _meta.boards[channel_id].
    """
    contenido = tablero_texto()
    boards = sistemas["_meta"]["boards"]
    channel_key = str(channel.id)
    msg_id = boards.get(channel_key)

    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(content=contenido)
            return
        except Exception:
            # el mensaje ya no existe o no es accesible -> creamos uno nuevo
            pass

    msg = await channel.send(contenido)
    boards[channel_key] = str(msg.id)
    save_data(sistemas)


# ======================
# Eventos
# ======================
@bot.event
async def on_ready():
    print(f"✅ Conectado como {bot.user}")


# ======================
# Comandos
# ======================
@bot.command()
async def agregar(ctx,
                  actividad: str,
                  sistema: str,
                  total: int,
                  tipo: str = "NUESTRA"):
    """
    Crea o ACTUALIZA una actividad.
    - Mantiene 'hecho' si ya existía.
    - Actualiza 'total' y 'tipo' al valor indicado.
    Uso:
      !agregar NDS_CORP KD 1 CORP
      !agregar NDS_NUESTRA G9 3 NUESTRA
      !agregar LUNAR KD 1 NUESTRA
    """
    s, a = sistema.upper(), actividad.upper()
    t = tipo.upper()

    if s not in sistemas:
        sistemas[s] = {}

    old_hecho = 0
    if a in sistemas[s] and isinstance(sistemas[s][a], dict):
        old_hecho = int(sistemas[s][a].get("hecho", 0))

    sistemas[s][a] = {"hecho": old_hecho, "total": int(total), "tipo": t}
    save_data(sistemas)
    await ctx.send(f"✅ {a} en {s} ahora tiene total {total} ({t}).")
    await actualizar_tablero(ctx.channel)


@bot.command()
async def registrar(ctx, actividad: str, sistema: str, quien: str = ""):
    """
    Suma +1 al progreso 'hecho' si aún no llegó al total.
    Uso:
      !registrar NDS_CORP KD
      !registrar NDS_NUESTRA G9
    """
    s, a = sistema.upper(), actividad.upper()
    if s not in sistemas or a not in sistemas[s] or not isinstance(
            sistemas[s][a], dict):
        await ctx.send("⚠️ Sistema o actividad no encontrada.")
        return

    hecho = int(sistemas[s][a].get("hecho", 0))
    total = int(sistemas[s][a].get("total", 0))
    if hecho < total:
        sistemas[s][a]["hecho"] = hecho + 1
        save_data(sistemas)
        etiqueta = f" ({quien})" if quien else ""
        await ctx.send(
            f"✅ Registrado {a} en {s}{etiqueta}: {hecho + 1}/{total}")
    else:
        await ctx.send(f"⚠️ {a} en {s} ya está completo ({hecho}/{total}).")
    await actualizar_tablero(ctx.channel)


@bot.command(aliases=["restar", "desregistrar", "undo"])
async def deshacer(ctx, actividad: str, sistema: str, cantidad: int = 1):
    """
    Resta 'cantidad' al progreso hecho (sin bajar de 0).
    Uso:
      !deshacer NDS_CORP KD          -> resta 1
      !deshacer NDS_CORP KD 2        -> resta 2
    Alias: !restar, !desregistrar, !undo
    """
    s, a = sistema.upper(), actividad.upper()
    if s not in sistemas or a not in sistemas[s] or not isinstance(
            sistemas[s][a], dict):
        await ctx.send("⚠️ Sistema o actividad no encontrada.")
        return

    if cantidad < 1:
        await ctx.send("⚠️ La cantidad debe ser >= 1.")
        return

    hecho = int(sistemas[s][a].get("hecho", 0))
    nuevo = max(0, hecho - int(cantidad))
    sistemas[s][a]["hecho"] = nuevo
    save_data(sistemas)

    total = int(sistemas[s][a].get("total", 0))
    await ctx.send(
        f"↩️ Deshecho {min(cantidad, hecho)} en {a} de {s}: {nuevo}/{total}")
    await actualizar_tablero(ctx.channel)


@bot.command()
async def quitar(ctx, actividad: str, sistema: str):
    """
    Elimina solo una actividad del sistema.
    Uso:
      !quitar NDS_CORP KD
    """
    s, a = sistema.upper(), actividad.upper()
    if s in sistemas and a in sistemas[s]:
        sistemas[s].pop(a)
        if not sistemas[s]:
            # si el sistema quedó vacío, lo quitamos
            sistemas.pop(s)
        save_data(sistemas)
        await ctx.send(f"🗑️ Eliminado {a} de {s}.")
    else:
        await ctx.send("⚠️ No existe ese sistema/actividad.")
    await actualizar_tablero(ctx.channel)


@bot.command()
async def reset(ctx):
    """
    Pone 'hecho = 0' en TODAS las actividades (no borra nada).
    Uso:
      !reset
    """
    for s, acts in list(sistemas.items()):
        if s == "_meta" or not isinstance(acts, dict):
            continue
        for a, dat in acts.items():
            if isinstance(dat, dict) and "hecho" in dat:
                dat["hecho"] = 0
    save_data(sistemas)
    await ctx.send("🔄 Contadores reseteados (sin borrar sistemas/actividades)."
                   )
    await actualizar_tablero(ctx.channel)


@bot.command()
async def mostrar(ctx):
    """
    Envía SIEMPRE la tabla actual como mensaje nuevo
    y además actualiza/crea el tablero fijo del canal.
    Uso:
      !mostrar
    """
    # manda una copia fresca en el chat para que la veas abajo
    await ctx.send(tablero_texto())
    # y actualiza/crea el tablero fijo arriba
    await actualizar_tablero(ctx.channel)


@bot.command()
async def ayuda(ctx):
    """
    Muestra la guía rápida de comandos.
    """
    texto = (
        "Comandos:\n"
        "!agregar [actividad] [sistema] [total] [tipo]\n"
        "   - Crea o ACTUALIZA la actividad (mantiene lo hecho)\n"
        "   - Ej: !agregar NDS_CORP KD 1 CORP\n"
        "   - Ej: !agregar NDS_NUESTRA G9 3 NUESTRA\n"
        "   - Ej: !agregar LUNAR KD 1 NUESTRA\n"
        "\n"
        "!registrar [actividad] [sistema] [quien]\n"
        "   - Suma +1 al progreso; opcionalmente indica quién\n"
        "   - Ej: !registrar NDS_NUESTRA KD cami\n"
        "\n"
        "!deshacer [actividad] [sistema] [cantidad]\n"
        "   - Resta al progreso (sin bajar de 0)\n"
        "   - Alias: !restar, !desregistrar, !undo\n"
        "\n"
        "!quitar [actividad] [sistema]\n"
        "   - Elimina la actividad del sistema\n"
        "   - Ej: !quitar LUNAR KD\n"
        "\n"
        "!reset\n"
        "   - Pone hecho=0 en TODAS las actividades (no borra nada)\n"
        "\n"
        "!mostrar\n"
        "   - Envía la tabla actual y actualiza el tablero fijo del canal\n")
    await ctx.send(f"```{texto}```")


# ======================
# Arranque
# ======================
if not TOKEN:
    raise SystemExit("Falta DISCORD_TOKEN en variables de entorno")
bot.run(TOKEN)
