import "./globals.css";

export const metadata = {
  title: "SoundLab — scores par titre",
  description: "Probabilité qu'un titre atteigne le quart supérieur des écoutes. Un score par titre, jamais par personne.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
