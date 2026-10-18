// Market: everything that helps you understand the market, in one place.
// Nothing here is a buy or sell call; those come from the model on the Today page.
import { NavLink, useLocation } from "react-router-dom";
import BeforeOpenPage from "./BeforeOpen";
import MarketPage from "./Market";
import NewsPage, { MoversPage } from "./News";

export const MARKET_TABS: [string, string][] = [
  ["/market", "Market health"], ["/before-open", "Before the open"],
  ["/movers", "Mood & movers"], ["/news", "News ideas"],
];

export default function MarketHub() {
  const { pathname } = useLocation();
  return (
    <>
      <nav className="subnav" aria-label="Market sections">
        {MARKET_TABS.map(([path, label]) => (
          <NavLink key={path} to={path} end className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
        ))}
      </nav>
      {pathname === "/before-open" ? <BeforeOpenPage />
        : pathname === "/movers" ? <MoversPage />
          : pathname === "/news" ? <NewsPage /> : <MarketPage />}
    </>
  );
}
