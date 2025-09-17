import os, json, pathlib
import discord
from discord.ext import commands

# ===== Config =====
PREFIX = "!"
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.getenv("DATA_FILE", "/data/sistemas.json")  # en Railway montaremos /data

# Intents: necesario para leer contenido de mensajes (!comandos)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ===== Datos =====
pathlib.Path(DATA_FILE).parent.mkdir(parents=True, exist_ok=True)

def load_data():
    if not pathlib.Path(DATA_FILE).exists():
        save_data({})
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

sistemas = load_data()
score_message_id = None  # si quieres persistirlo, guárdalo en el JSON

def tablero_texto():
    if not sistemas:
        return "**📋 Estado de Actividades**\n_(vacío; usa `!agregar ...`)_"
    lineas = ["**📋 Estado de Actividades**"]
    for sistema, acts in sistemas.items():
        lineas.append(f"**{sistema}**")
        for act, dat in acts.items():
            tipo = dat.get("tipo", "N/A")
            lineas.append(f" → {act} ({tipo}): {dat['hecho']}/{dat['total']}")
    return "\n".join(lineas)

async def actualizar_tablero(channel: discord.TextChannel):
    global score_message_id
    if score_message_id:
        try:
            msg = await channel.fetch_message(score_message_id)
            await msg.edit(content=tablero_texto())
            return
        except Exception:
            pass
    msg = await channel.send(tablero_texto())
    score_message_id = msg.id

@bot.event
async def on_ready():
    print(f"✅ Conectado como {bot.user}")

@bot.command()
async def agregar(ctx, actividad: str, sistema: str, total: int, tipo: str = "NUESTRA"):
    s, a = sistema.upper(), actividad.upper()
    sistemas.setdefault(s, {})[a] = {"hecho": 0, "total": int(total), "tipo": tipo.upper()}
    save_data(sistemas)
    await ctx.send(f"➕ Agregado {a} en {s} ({tipo.upper()}) con {total}.")
    await actualizar_tablero(ctx.channel)

@bot.command()
async def registrar(ctx, actividad: str, sistema: str, quien: str = ""):
    s, a = sistema.upper(), actividad.upper()
    if s not in sistemas or a not in sistemas[s]:
        await ctx.send("⚠️ Sistema o actividad no encontrada.")
        return
    if sistemas[s][a]["hecho"] < sistemas[s][a]["total"]:
        sistemas[s][a]["hecho"] += 1
        save_data(sistemas)
        await ctx.send(f"✅ Registrado {a} en {s} ({quien or ctx.author.name})")
    else:
        await ctx.send(f"⚠️ Ya se completó el máximo en {s} para {a}.")
    await actualizar_tablero(ctx.channel)

@bot.command()
async def quitar(ctx, actividad: str, sistema: str):
    s, a = sistema.upper(), actividad.upper()
    if s in sistemas and a in sistemas[s]:
        sistemas[s].pop(a)
        if not sistemas[s]:
            sistemas.pop(s)
        save_data(sistemas)
        await ctx.send(f"🗑️ Eliminado {a} de {s}.")
    else:
        await ctx.send("⚠️ No existe ese sistema/actividad.")
    await actualizar_tablero(ctx.channel)

@bot.command()
async def reset(ctx):
    for s, acts in sistemas.items():
        for a in acts:
            sistemas[s][a]["hecho"] = 0
    save_data(sistemas)
    await ctx.send("🔄 Semana reseteada.")
    await actualizar_tablero(ctx.channel)

@bot.command()
async def mostrar(ctx):
    await actualizar_tablero(ctx.channel)

@bot.command()
async def ayuda(ctx):
    texto = (
        "Comandos:\n"
        "!agregar [actividad] [sistema] [total] [tipo]\n"
        "!registrar [actividad] [sistema] [quien]\n"
        "!quitar [actividad] [sistema]\n"
        "!reset\n"
        "!mostrar\n"
    )
    await ctx.send(f"```{texto}```")

if not TOKEN:
    raise SystemExit("Falta DISCORD_TOKEN en variables de entorno")
bot.run(TOKEN)
