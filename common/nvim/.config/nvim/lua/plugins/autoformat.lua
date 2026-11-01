return {
	-- Autoformat
	"stevearc/conform.nvim",
	lazy = false,
	dependencies = {
		{
			"WhoIsSethDaniel/mason-tool-installer.nvim",
			dependencies = { "mason-org/mason.nvim" },
			opts = { ensure_installed = { "prettier" } },
		},
	},
	keys = {
		{
			"<leader>f",
			function()
				require("conform").format({ async = true, lsp_fallback = true })
			end,
			mode = "",
			desc = "[F]ormat buffer",
		},
	},
	opts = {
		notify_on_error = false,
		format_on_save = {
			timeout_ms = 500,
			lsp_fallback = true,
		},
		formatters_by_ft = {
			lua = { "stylua" },
			-- Conform can also run multiple formatters sequentially
			python = { "isort", "black" },
			markdown = { "prettier" },
			-- javascript = { { "prettierd", "prettier" } },
			json = { "prettierd", "prettier" },
		},
		formatters = {
			black = {
				prepend_args = { "--line-length", "100" },
				timeout_ms = 5500,
			},
		},
	},
}
