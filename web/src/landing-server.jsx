import { renderToString } from "react-dom/server";
import { LandingPage } from "./landing";

/** Renders the public landing page into static HTML during the production build. */
export function renderLanding() {
  return renderToString(<LandingPage />);
}
