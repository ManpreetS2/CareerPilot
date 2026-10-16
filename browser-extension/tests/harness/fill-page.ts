import { fillFormInPage } from "../../src/fillForm";

declare global {
  interface Window {
    fillFormInPage: typeof fillFormInPage;
  }
}

window.fillFormInPage = fillFormInPage;
