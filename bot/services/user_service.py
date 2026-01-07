
class UserService:
    @staticmethod
    async def get_user_stats(user_id: int):
        """Получить статистику пользователя"""
        return {
            "total_ads": 0,
            "active_ads": 0,
            "views": 0
        }
