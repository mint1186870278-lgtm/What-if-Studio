import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.js"],
    languageOptions: {
      sourceType: "module",
      globals: {
        ...globals.browser
      }
    },
    rules: {
      "no-console": "off"
    }
  },
  {
    files: ["test/**/*.js"],
    languageOptions: {
      sourceType: "module",
      globals: {
        ...globals.node
      }
    }
  }
];
