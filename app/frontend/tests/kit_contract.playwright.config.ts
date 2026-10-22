import config from "../playwright.config";

// Contract specs intercept the bundled UI and all APIs; never launch the app.
export default { ...config, testDir: ".", webServer: undefined };
