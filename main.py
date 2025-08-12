import os
import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, ButtonStyle, SelectOption
from nextcord.ui import View, Button, Select
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

config = {
    "Бронижелет": 20,
    "Кайданки": 25,  # 25 materials craft 5 handcuffs
    "Сухпайок": 10,
    "Тазер": 20,
    "9x19": 1,  # 1 material crafts 10 rounds of ammo
    "12/70": 1,
    "7.62": 1,
    "5.56": 1,
    ".45 ACP": 1,
    ".338": 1,
    "Поліпшена гвинтівка": 80,
    "Буллап": 80,
    "Сайга": 48,
    "Важкий пістолет": 24,
    "Пістолет Мк. 2": 24,
}

user_crafting_data = {}


class CraftingBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=nextcord.Intents.default())
        self.reset_daily_limits.start()

    async def on_ready(self):
        print(f"Bot is ready. Logged in as {self.user}")

    @tasks.loop(time=datetime.strptime("00:00:00", "%H:%M:%S").time())
    async def reset_daily_limits(self):
        # Reset user crafting limits at midnight Kyiv time
        kyiv_tz = pytz.timezone('Europe/Kyiv')
        current_time = datetime.now(kyiv_tz)
        if current_time.time() >= self.reset_daily_limits.time:
            user_crafting_data.clear()
            print("User crafting limits have been reset.")


class LevelSelectView(View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.level_select = Select(
            placeholder="Виберіть рівень зброяра",
            options=[
                SelectOption(label="Рівень 1", value="1"),
                SelectOption(label="Рівень 2", value="2"),
                SelectOption(label="Рівень 3", value="3"),
                SelectOption(label="Рівень 4", value="4"),
                SelectOption(label="Рівень 5", value="5"),
            ]
        )
        self.level_select.callback = self.level_select_callback
        self.add_item(self.level_select)

    async def level_select_callback(self, interaction: Interaction):
        level = int(interaction.data['values'][0])
        view = CraftView(self.user_id, level)
        view.message = await interaction.response.edit_message(content="Виберіть предмети для крафту:", view=view)


class CraftView(View):
    def __init__(self, user_id, level):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.level = level
        self.discount = (level - 1) * 0.1  # 10% per level starting from level 2
        self.item_counts = {item: 0 for item in config.keys()}
        user_data = user_crafting_data.get(user_id, {"total_materials": 0, "last_reset": datetime.now(pytz.timezone('Europe/Kyiv'))})
        self.starting_total_materials = user_data["total_materials"]  # Store the initial materials used
        self.total_materials = user_data["total_materials"]
        self.materials_used_button = Button(label=f"Всього використано матеріалів: {self.total_materials}/500", style=ButtonStyle.gray, disabled=True)
        self.add_item_buttons()
        self.add_control_buttons()
        self.add_item(self.materials_used_button)

        # Initialize user crafting data if not already present
        if user_id not in user_crafting_data:
            user_crafting_data[user_id] = {
                "total_materials": 0,
                "last_reset": datetime.now(pytz.timezone('Europe/Kyiv'))
            }

    def add_item_buttons(self):
        for item in self.item_counts.keys():
            button = Button(label=f"{item} (x0)", style=ButtonStyle.primary, custom_id=item)
            button.callback = self.item_button_callback
            self.add_item(button)

    def add_control_buttons(self):
        done_button = Button(label="", emoji="✅", style=ButtonStyle.success, custom_id="done")
        done_button.callback = self.done_button_callback
        clear_button = Button(label="", emoji="🧹", style=ButtonStyle.danger, custom_id="clear")
        clear_button.callback = self.clear_button_callback
        self.add_item(done_button)
        self.add_item(clear_button)

    async def item_button_callback(self, interaction: Interaction):
        item = interaction.data['custom_id']
        increment = 10 if item in ["9x19", "12/70", "7.62", "5.56", ".45 ACP",
                                   ".338"] else 5 if item == "Кайданки" else 1
        base_materials_needed = increment // (
            5 if item == "Кайданки" else 10 if item in ["9x19", "12/70", "7.62", "5.56", ".45 ACP", ".338"] else 1) * \
                           config[item]
        if item not in ["9x19", "12/70", "7.62", "5.56", ".45 ACP", ".338", "Бронижелет", "Кайданки"]:
            materials_needed = int(base_materials_needed * (1 - self.discount))
        else:
            materials_needed = base_materials_needed

        user_data = user_crafting_data[self.user_id]
        if user_data["total_materials"] + materials_needed > 500:
            await interaction.response.send_message("Ви досягли ліміту в 500 матеріалів.", ephemeral=True)
            return

        self.item_counts[item] += increment
        self.total_materials += materials_needed
        user_data["total_materials"] += materials_needed

        for item_button in self.children:
            if item_button.custom_id == item:
                item_button.label = f"{item} (x{self.item_counts[item]})"

        self.materials_used_button.label = f"Всього використано матеріалів: {self.total_materials}/500"
        await interaction.response.edit_message(view=self)

    async def done_button_callback(self, interaction: Interaction):
        await self.send_summary(interaction)

    async def clear_button_callback(self, interaction: Interaction):
        user_data = user_crafting_data[self.user_id]
        user_data["total_materials"] = self.starting_total_materials  # Reset to initial materials used

        self.item_counts = {key: 0 for key in self.item_counts}
        self.total_materials = self.starting_total_materials  # Reset to initial materials used
        for item_button in self.children:
            if item_button.custom_id in self.item_counts:
                item_button.label = f"{item_button.custom_id} (x0)"
        self.materials_used_button.label = f"Всього використано матеріалів: {self.total_materials}/500"
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    async def send_summary(self, interaction: Interaction):
        kyiv_time = datetime.now(pytz.timezone('Europe/Kyiv')).strftime("%H:%M:%S")
        summary = f"<@{self.user_id}> | {kyiv_time}\n"
        for item, count in self.item_counts.items():
            if count > 0:
                base_materials_used = count // (
                    5 if item == "Кайданки" else 10 if item in ["9x19", "12/70", "7.62", "5.56", ".45 ACP",
                                                                ".338"] else 1) * config[item]
                if item not in ["9x19", "12/70", "7.62", "5.56", ".45 ACP", ".338", "Бронижелет", "Кайданки"]:
                    materials_used = int(base_materials_used * (1 - self.discount))
                else:
                    materials_used = base_materials_used
                summary += f"{item} - {count} шт. {materials_used} мат.\n"
        summary += f"Всього використано матеріалів: {self.total_materials}/500 ({self.level} рівень)"
        await interaction.channel.send(summary)
        await interaction.response.edit_message(content="Звіт крафту надіслано!", view=None)


bot = CraftingBot()


@bot.slash_command(guild_ids=[GUILD_ID], description="Відкрити меню крафту")
async def craft(interaction: Interaction):
    if interaction.channel.id != CHANNEL_ID:
        await interaction.response.send_message("Ви можете використовувати цю команду лише у призначеному каналі.",
                                                ephemeral=True)
        return
    view = LevelSelectView(interaction.user.id)
    view.message = await interaction.response.send_message("Виберіть рівень зброяра:", view=view, ephemeral=True)


bot.run(TOKEN)
