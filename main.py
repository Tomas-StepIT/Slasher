import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sqlite3
import re 
import time
import requests
from bs4 import BeautifulSoup 

load_dotenv()

# --- Konstanty ---
TOKEN = os.getenv('DISCORD_TOKEN')
DB_FILE = "hlidac_cen.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Databáze
def setup_database():
    print("🔷 Starting database setup...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            target_price REAL NOT NULL,
            css_selector TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ Database setup successful")


def vycistit_cenu(text_ceny: str): 
    try:
        cista_cena = re.sub(r"[^0-9,.]", "", text_ceny)
        cista_cena = cista_cena.replace(',', '.')
        if cista_cena.count('.') > 1:
            cista_cena = cista_cena.replace('.', '', cista_cena.count('.') - 1)
        return float(cista_cena)
    except Exception as e:
        print(f"Chyba při čištění ceny '{text_ceny}': {e}")
        return None

# Pro čtení zpráv
intents = discord.Intents.default()
intents.message_content = True

# Prefix pro příkazy (vykříčník a pak bude příkaz)
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None) 

# Když se bot úspěšně připojí k Discord serveru, vypíše zprávu
@bot.event
async def on_ready():
    print(f'✅ Přihlášen jako {bot.user}')

# Testovací příkaz ping-pong
@bot.command()
async def ping(ctx: commands.Context[commands.Bot]):
    start = time.perf_counter()
    message = await ctx.send("Pong!")
    end = time.perf_counter()
    latency_ms = (end - start) * 1000
    await message.edit(content=f"Pong! {latency_ms:.2f} ms")

@bot.command()
async def slap (ctx: commands.Context[commands.Bot], member: discord.Member):
    await ctx.send(f"{ctx.author.mention} plácnul {member.mention}")


@bot.command()
async def help(ctx: commands.Context[commands.Bot]): 
    embed = discord.Embed(
        title="Nápověda - Hlídač cen",
        description="Jsem bot, který za tebe pohlídá ceny produktů na webu.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="!pridat <jméno> <url> <cena> \"<selektor>\"",
        value="Přidá nový produkt ke sledování.\n"
                "**Jméno:** Tvoje přezdívka (např. \"Klíčenka YubiKey\")\n"
                "**URL:** Plný odkaz na produkt\n"
                "**Cena:** Číslo, např. `1200`\n"
                "**Selektor:** CSS selektor ceny, **v uvozovkách** (např. `\"span.price-box__price\"`)",
        inline=False
    )
    embed.add_field(
        name="!seznam",
        value="Vypíše všechny tvé sledované produkty, včetně aktuální ceny.",
        inline=False
    )
    embed.add_field(
        name="!smazat <ID>",
        value="Smaže produkt ze sledování podle jeho ID (které uvidíš v `!seznam`).",
        inline=False
    )
    embed.add_field(
        name="!help",
        value="Zobrazí tuto nápovědu.",
        inline=False
    )
    await ctx.send(embed=embed)


@bot.command()
async def pridat(ctx: commands.Context[commands.Bot], name: str, url: str, target_price: float, selector: str):
    user_id = ctx.author.id
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO products (user_id, name, url, target_price, css_selector) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, url, target_price, selector)
        )
        
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ **Uloženo!** Budu sledovat produkt **{name}**.\n"
                       f"Oznámím ti, až cena klesne pod **{target_price} Kč**.")
    
    except sqlite3.Error as e:
        await ctx.send(f"❌ Chyba při ukládání do databáze: {e}")
    except Exception as e:
        await ctx.send(f"❌ Vyskytla se nečekaná chyba: {e}")


@bot.command()
async def smazat(ctx: commands.Context[commands.Bot], product_id: int):
    user_id = ctx.author.id
    
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM products WHERE id = ? AND user_id = ?", (product_id, user_id))
        product = cursor.fetchone()
        
        if not product:
            await ctx.send(f"❌ Chyba: Produkt s ID `{product_id}` nebyl nalezen nebo ti nepatří.")
            conn.close()
            return

        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
        
        await ctx.send(f"🗑️ **Smazáno!** Produkt **{product['name']}** (ID: `{product_id}`) byl odebrán.")
        
    except sqlite3.Error as e:
        await ctx.send(f"Chyba při mazání z databáze: {e}")
    except Exception as e:
        await ctx.send(f"Vyskytla se nečekaná chyba: {e}")


@bot.command()
async def seznam(ctx: commands.Context[commands.Bot]): 
    user_id = ctx.author.id
    
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products WHERE user_id = ?", (user_id,))
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            await ctx.send("Zatím nesleduješ žádné produkty. Přidej si nějaký pomocí `!pridat`.")
            return

        await ctx.send(f"Prohledávám weby... Nalezeno {len(products)} produktů, to může chvilku trvat.")

        embed = discord.Embed(
            title=f"Tvoje sledované produkty ({len(products)})", 
            color=discord.Color.blue()
        )
        
        for prod in products:
            aktualni_cena_str = "Neznámá"
            rozdil_str = ""
            barva_ikony = "⚪" # Bílá pro chybu
            
            try:
                # Pro každý produkt stáhneme aktuální data
                response = requests.get(prod['url'], headers=HEADERS)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    element_ceny = soup.select_one(prod['css_selector'])
                    
                    if element_ceny:
                        aktualni_cena = vycistit_cenu(element_ceny.get_text().strip())
                        if aktualni_cena is not None:
                            aktualni_cena_str = f"**{aktualni_cena} Kč**"
                            rozdil = aktualni_cena - prod['target_price']
                            
                            if rozdil <= 0:
                                rozdil_str = f" (Cíl splněn o {-rozdil} Kč!)"
                                barva_ikony = "✅" # Zelená
                            else:
                                rozdil_str = f" (Chybí {rozdil} Kč)"
                                barva_ikony = "🔴" # Červená
                        else:
                            aktualni_cena_str = "Chyba při čištění ceny"
                    else:
                        aktualni_cena_str = "Selektor nenalezen"
                else:
                    aktualni_cena_str = f"Chyba {response.status_code}"

            except Exception as e:
                print(f"Chyba při stahování {prod['url']}: {e}")
                aktualni_cena_str = "Chyba stahování"

            # Přidáme políčko do embedu
            embed.add_field(
                name=f"{barva_ikony} {prod['name']} (ID: {prod['id']})",
                value=f"Cíl: {prod['target_price']} Kč | Nyní: {aktualni_cena_str}{rozdil_str}\n"
                      f"URL: <{prod['url']}>",
                inline=False
            )
        
        embed.set_footer(text="Produkt můžeš smazat pomocí !smazat <ID>")
        await ctx.send(embed=embed)
        
    except sqlite3.Error as e:
        await ctx.send(f"❌ Chyba při čtení z databáze: {e}")
    except Exception as e:
        await ctx.send(f"❌ Vyskytla se nečekaná chyba: {e}")


if __name__ == "__main__":
    print("🔷 Starting...")
    
    setup_database()
    
    print("🔷 Starting discord bot...")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Error: Missing discord token") 