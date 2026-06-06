import polars as pl

def calculate_ranking(palpites_df: pl.DataFrame, gabarito_df: pl.DataFrame, users_df: pl.DataFrame) -> pl.DataFrame:
    """
    Calcula a classificação do bolão vetorizada usando Polars.
    Retorna um DataFrame ordenado com Nome, Pontos, Acertos de Placar e Acertos de Vencedor.
    """
    if palpites_df.is_empty() or gabarito_df.is_empty():
        return format_empty_ranking(users_df)

    # Filtrar gabarito para apenas jogos que já ocorreram (tem placar)
    gabarito_valid = gabarito_df.filter(
        pl.col("gols_a").is_not_null() & pl.col("gols_b").is_not_null()
    )

    if gabarito_valid.is_empty():
        return format_empty_ranking(users_df)

    # Join
    df = palpites_df.join(
        gabarito_valid,
        on="match_id",
        how="inner",
        suffix="_gab"
    )

    # Filtra palpites válidos
    df = df.filter(
        pl.col("gols_a").is_not_null() & pl.col("gols_b").is_not_null()
    )

    if df.is_empty():
        return format_empty_ranking(users_df)

    # Calcula condições
    exact_match = (pl.col("gols_a") == pl.col("gols_a_gab")) & (pl.col("gols_b") == pl.col("gols_b_gab"))
    
    tendency_palpite = pl.when(pl.col("gols_a") > pl.col("gols_b")).then(pl.lit(1)) \
                         .when(pl.col("gols_a") < pl.col("gols_b")).then(pl.lit(-1)) \
                         .otherwise(pl.lit(0))
                         
    tendency_gab = pl.when(pl.col("gols_a_gab") > pl.col("gols_b_gab")).then(pl.lit(1)) \
                     .when(pl.col("gols_a_gab") < pl.col("gols_b_gab")).then(pl.lit(-1)) \
                     .otherwise(pl.lit(0))
                     
    tendency_match = tendency_palpite == tendency_gab

    # Atribui pontos
    df = df.with_columns(
        pl.when(exact_match).then(pl.lit(3))
          .when(tendency_match).then(pl.lit(1))
          .otherwise(pl.lit(0))
          .alias("pontos")
    )

    # Agregação
    ranking = df.group_by("user_id").agg([
        pl.col("pontos").sum().alias("Pontos"),
        (pl.col("pontos") == 3).sum().alias("Acertos de Placar (3pts)"),
        (pl.col("pontos") == 1).sum().alias("Acertos de Vencedor (1pt)")
    ])

    # Traz os usuários que não palpitaram ou não pontuaram
    ranking = users_df.join(ranking, on="user_id", how="left")
    
    # Preenche nulos com 0
    ranking = ranking.fill_null(0)

    # Ordenação: Pontos DESC, Placar Exato DESC, Vencedor DESC
    ranking = ranking.sort(
        by=["Pontos", "Acertos de Placar (3pts)", "Acertos de Vencedor (1pt)"],
        descending=[True, True, True]
    )

    # Formata a saída
    ranking = ranking.select([
        pl.col("name").alias("Nome"),
        pl.col("Pontos"),
        pl.col("Acertos de Placar (3pts)"),
        pl.col("Acertos de Vencedor (1pt)")
    ])

    # Adiciona rank
    ranking = ranking.with_columns(
        pl.arange(1, ranking.height + 1).alias("Rank")
    ).select(["Rank", "Nome", "Pontos", "Acertos de Placar (3pts)", "Acertos de Vencedor (1pt)"])

    return ranking

def format_empty_ranking(users_df: pl.DataFrame) -> pl.DataFrame:
    if users_df.is_empty():
        return pl.DataFrame({
            "Rank": pl.Series(dtype=pl.Int64),
            "Nome": pl.Series(dtype=pl.Utf8),
            "Pontos": pl.Series(dtype=pl.Int64),
            "Acertos de Placar (3pts)": pl.Series(dtype=pl.UInt32),
            "Acertos de Vencedor (1pt)": pl.Series(dtype=pl.UInt32)
        })
    df = users_df.select(pl.col("name").alias("Nome")).with_columns([
        pl.lit(0).alias("Pontos"),
        pl.lit(0).alias("Acertos de Placar (3pts)"),
        pl.lit(0).alias("Acertos de Vencedor (1pt)")
    ]).sort("Nome")
    df = df.with_columns(
        pl.arange(1, df.height + 1).alias("Rank")
    ).select(["Rank", "Nome", "Pontos", "Acertos de Placar (3pts)", "Acertos de Vencedor (1pt)"])
    return df
