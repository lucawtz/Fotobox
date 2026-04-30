import { ReactNode } from "react";
import { Paper, Box, Typography, Stack } from "@mui/material";

interface Props {
  title: string;
  description?: string;
  icon?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export default function SettingsCard({ title, description, icon, children, footer }: Props) {
  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: 3,
        border: "1px solid",
        borderColor: "divider",
        overflow: "hidden",
      }}
    >
      <Box sx={{ p: { xs: 1.75, sm: 3 } }}>
        <Stack
          direction="row"
          spacing={{ xs: 1.25, sm: 2 }}
          alignItems="flex-start"
          sx={{ mb: description ? 0.5 : 0 }}
        >
          {icon && (
            <Box
              sx={{
                width: { xs: 36, sm: 40 },
                height: { xs: 36, sm: 40 },
                borderRadius: 2,
                display: "grid", placeItems: "center",
                bgcolor: "#e8f0fe",
                color: "primary.main",
                flexShrink: 0,
                "& > svg": { fontSize: { xs: 20, sm: 24 } },
              }}
            >
              {icon}
            </Box>
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="h6"
              sx={{
                fontWeight: 600,
                fontSize: { xs: ".95rem", sm: "1.05rem" },
                lineHeight: 1.3,
              }}
            >
              {title}
            </Typography>
            {description && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 0.25, fontSize: { xs: ".8rem", sm: ".875rem" } }}
              >
                {description}
              </Typography>
            )}
          </Box>
        </Stack>
        <Box sx={{ mt: { xs: 1.75, sm: 2.5 } }}>{children}</Box>
      </Box>
      {footer && (
        <Box
          sx={{
            px: { xs: 2.25, sm: 3 },
            py: 1.5,
            bgcolor: "grey.50",
            borderTop: "1px solid",
            borderColor: "divider",
            display: "flex",
            justifyContent: "flex-end",
            gap: 1,
          }}
        >
          {footer}
        </Box>
      )}
    </Paper>
  );
}
