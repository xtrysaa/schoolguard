import "./globals.css";

export const metadata = {
  title: "SchoolGuard — ИИ против буллинга",
  description: "Система раннего выявления признаков буллинга по видео: скелеты, траектории, Risk Score и проверка человеком.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
