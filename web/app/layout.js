import "./globals.css";
import { Golos_Text, JetBrains_Mono } from "next/font/google";

const sans = Golos_Text({ subsets: ["latin", "cyrillic"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin", "cyrillic"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata = {
  title: "SchoolGuard — раннее предупреждение о драках и травле в школе",
  description: "Программа для Windows: подключается к школьным камерам, замечает признаки драки по движениям людей и отправляет видеозапись момента психологу в Telegram. Лица закрыты, решение принимает человек.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
